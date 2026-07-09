"""
RAG retriever — HYBRID search over per-agent KB chunks in PostgreSQL.

Order of retrieval:
  1. Vector / semantic search (pgvector, cosine via `<=>`) — primary. Catches
     paraphrases and meaning even when no words overlap.
  2. Full-text search (to_tsvector) + ILIKE keyword search — top-up / fallback.
     Great for exact system names (ESAF, NexID, TMS) that embeddings can blur,
     and a safety net when embeddings are missing or the query is punctuation.

Results from all stages are merged and de-duplicated by content, capped at top_k.
The DB does the heavy lifting; Python only merges.
"""
import hashlib
import logging

from sqlalchemy import text

from backend.config import settings
from backend.database import SessionLocal
from backend.services.embeddings import embed_query, to_pgvector_literal
from backend.services.redis.cache import get_cache

log = logging.getLogger("rag")


async def retrieve(agent_id, query: str, top_k: int | None = None, original_text: str = "") -> list[str]:
    """Return the most relevant KB chunks for `query`, scoped to `agent_id`.

    If `original_text` is provided (e.g. the raw user utterance in Bengali/Hindi),
    it is also searched via ILIKE and merged with the keyword-query results so that
    domain terms missed by keyword extraction can still be found.
    """
    query = query.strip()
    if not query:
        return []
    if top_k is None:
        top_k = settings.KB_TOP_K
    

    # ── cache lookup ──────────────────────────────────
    cache = get_cache()
    raw = f"{agent_id}|{query}|{original_text}|{top_k}"
    cache_key = f"kb:{hashlib.md5(raw.encode()).hexdigest()}"
    try:
        cached = await cache.get_json(cache_key)
        if cached is not None:
            log.info("SOURCE=REDIS_CACHE | query=%r | chunks=%d", query[:60], len(cached))
            return cached
    except Exception:
        log.exception("cache read failed — using DB")

    db = SessionLocal()
    try:
        agent_id_str = str(agent_id)
        seen: set[str] = set()
        results: list[str] = []

        def _add(rows):
            for row in rows:
                content = row[0]
                filename = row[1]
                formatted_chunk = f"[Source: {filename}]\n{content}"
                if content not in seen:
                    seen.add(content)
                    results.append(formatted_chunk)

        # ── 0. VECTOR / SEMANTIC search (primary) ─────────────────────────
        # Embed the query and rank chunks by cosine distance. Keep only rows
        # above the similarity threshold so weak matches don't leak in.
        try:
            qvec = await embed_query(original_text or query)
            if qvec is not None:
                qlit = to_pgvector_literal(qvec)
                max_distance = 1.0 - settings.KB_MIN_SIMILARITY_SCORE
                vec_rows = db.execute(
                    text("""
                        SELECT content, filename,
                               1 - (embedding <=> CAST(:qvec AS halfvec)) AS similarity
                        FROM kb_chunks
                        WHERE agent_id = CAST(:aid AS UUID)
                          AND embedding IS NOT NULL
                          AND (embedding <=> CAST(:qvec AS halfvec)) <= :maxd
                        ORDER BY embedding <=> CAST(:qvec AS halfvec)
                        LIMIT :k
                    """),
                    {"aid": agent_id_str, "qvec": qlit, "maxd": max_distance, "k": top_k},
                ).fetchall()
                if vec_rows:
                    log.info(
                        "VECTOR returned %d chunks (top sim=%.3f) for: %s",
                        len(vec_rows), vec_rows[0][2], query[:60],
                    )
                    _add(vec_rows)
        except Exception:
            log.exception("vector search error — falling back to keyword search")

        # ── 1. FTS on extracted keywords (OR logic) — top-up if vector short ─
        try:
            words = [w.strip() for w in query.split() if len(w.strip()) > 2]
            if words and len(results) < top_k:
                or_query = " OR ".join(words)
                fts_rows = db.execute(
                    text("""
                        SELECT content, filename,
                               ts_rank(to_tsvector('english', content),
                                       websearch_to_tsquery('english', :q)) AS rank
                        FROM kb_chunks
                        WHERE agent_id = CAST(:aid AS UUID)
                          AND to_tsvector('english', content)
                              @@ websearch_to_tsquery('english', :q)
                        ORDER BY rank DESC
                        LIMIT :k
                    """),
                    {"aid": agent_id_str, "q": or_query, "k": top_k},
                ).fetchall()
                if fts_rows:
                    log.info("FTS returned %d chunks for: %s", len(fts_rows), query[:60])
                    _add(fts_rows)
        except Exception:
            log.exception("FTS search error")

        # ── 2. ILIKE on keywords (catches terms FTS misses) ──────────────
        if len(results) < top_k:
            words = [w.strip() for w in query.split() if len(w.strip()) > 2]
            if words:
                remaining = top_k - len(results)
                ilike_rows = _ilike_search(db, agent_id_str, words, remaining + 2)
                if ilike_rows:
                    log.info("ILIKE (keywords) returned %d chunks", len(ilike_rows))
                    _add(ilike_rows)

        # ── 3. ILIKE on original user text (catches domain-name mismatches) ─
        if original_text and len(results) < top_k:
            orig_words = [w.strip() for w in original_text.split() if len(w.strip()) > 2]
            # Only ASCII words (Bengali script won't match English KB anyway)
            ascii_words = [w for w in orig_words if w.isascii()]
            if ascii_words:
                remaining = top_k - len(results)
                orig_rows = _ilike_search(db, agent_id_str, ascii_words, remaining + 2)
                if orig_rows:
                    log.info("ILIKE (original text) returned %d extra chunks", len(orig_rows))
                    _add(orig_rows)

        log.info("SOURCE=KNOWLEDGE_BASE(DB) | query=%r | chunks=%d", query[:60], len(results))
        try:
            await cache.set_json(cache_key, results[:top_k], ttl=settings.KB_QUERY_CACHE_TTL)
        except Exception:
            log.exception("cache write failed — ignoring")
        return results[:top_k]

    except Exception:
        log.exception("RAG retrieve error")
        return []
    finally:
        db.close()


def _ilike_search(db, agent_id_str: str, words: list[str], limit: int):
    conditions = " OR ".join(f"content ILIKE :w{i}" for i in range(len(words)))
    params = {"aid": agent_id_str, "k": limit}
    params.update({f"w{i}": f"%{w}%" for i, w in enumerate(words)})
    try:
        return db.execute(
            text(f"""
                SELECT content, filename,
                       {_word_count_sql(words)} AS score
                FROM kb_chunks
                WHERE agent_id = CAST(:aid AS UUID)
                  AND ({conditions})
                ORDER BY score DESC
                LIMIT :k
            """),
            params,
        ).fetchall()
    except Exception:
        log.exception("ILIKE search error")
        return []


def _word_count_sql(words: list[str]) -> str:
    """Build a SQL expression that counts total keyword occurrences in content."""
    if not words:
        return "0"
    parts = [
        f"(LENGTH(content) - LENGTH(REPLACE(LOWER(content), LOWER(:w{i}), ''))) "
        f"/ NULLIF(LENGTH(:w{i}), 0)"
        for i in range(len(words))
    ]
    return "(" + " + ".join(parts) + ")"


def build_context_prompt(system_prompt: str, chunks: list[str]) -> str:
    if not chunks:
        return system_prompt
    context = "\n\n---\n\n".join(chunks)
    return (
        f"{system_prompt}\n\n"
        "Use the following knowledge base excerpts to answer. "
        "If the answer is not in the excerpts, say you don't have that information.\n\n"
        f"Knowledge Base:\n{context}"
    )

# ══════════════════════════════════════════════════════════════════════════
# STRUCTURED TROUBLESHOOTING ROUTER (kb_entries + policy_rules)
# ══════════════════════════════════════════════════════════════════════════
# Decides, per query, whether the agent should:
#   - LLM_ANSWERED : deep-dive dynamically, grounded strictly in KB steps, or
#   - KB_FETCH     : speak the policy/KB line verbatim, collect info, escalate.
# The choice is NOT left to the LLM — it's driven by the matched entry's
# answer_mode / policy_rule_ref columns. Low-confidence matches return None so
# the caller can fall back to the generic document-chunk RAG (retrieve()).


async def retrieve_entry(agent_id, query: str, original_text: str = "") -> dict | None:
    """Find the best troubleshooting entry for the query and resolve its route.

    Returns a decision dict {mode, entry, policy, similarity} or None when no
    entry matches confidently (caller should then fall back to chunk RAG).
    """
    q = (original_text or query or "").strip()
    if not q:
        return None
    qvec = await embed_query(q)
    if qvec is None:
        return None
    qlit = to_pgvector_literal(qvec)

    db = SessionLocal()
    try:
        aid = str(agent_id)
        row = db.execute(
            text("""
                SELECT entry_id, title, category, checklist_steps, probing_questions,
                       answer_mode, max_steps, policy_boundary, transfer_trigger,
                       transfer_after_step, transfer_priority, transfer_to,
                       info_to_collect, transfer_script, escalation_action,
                       policy_rule_ref,
                       1 - (embedding <=> CAST(:q AS halfvec)) AS similarity
                FROM kb_entries
                WHERE agent_id = CAST(:a AS UUID) AND embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:q AS halfvec)
                LIMIT 1
            """),
            {"a": aid, "q": qlit},
        ).mappings().first()

        if not row:
            return None
        sim = float(row["similarity"])
        if sim < settings.KB_MIN_SIMILARITY_SCORE:
            log.info("ROUTER no confident entry (top sim=%.3f) — fallback", sim)
            return None

        entry = dict(row)

        # Resolve a governing policy rule, if the entry references one.
        policy = None
        pref = (entry.get("policy_rule_ref") or "").strip()
        if pref:
            prow = db.execute(
                text("""
                    SELECT rule_id, policy_area, rule_statement, agent_says,
                           transfer_priority
                    FROM policy_rules
                    WHERE agent_id = CAST(:a AS UUID) AND rule_id = :rid
                    LIMIT 1
                """),
                {"a": aid, "rid": pref},
            ).mappings().first()
            if prow:
                policy = dict(prow)

        mode = "LLM_ANSWERED"
        if policy or (entry.get("answer_mode") or "").lower().startswith("kb-fetch"):
            mode = "KB_FETCH"

        return {"mode": mode, "entry": entry, "policy": policy, "similarity": sim}
    except Exception:
        log.exception("retrieve_entry error")
        return None
    finally:
        db.close()


def _clean(v) -> str:
    return (str(v).strip() if v is not None else "")


def build_router_prompt(base_system: str, decision: dict) -> str:
    """Turn a routing decision into the system prompt for this turn."""
    entry = decision["entry"]
    policy = decision.get("policy")
    mode = decision["mode"]

    if mode == "KB_FETCH":
        verbatim = _clean((policy or {}).get("agent_says")) or _clean(entry.get("escalation_action"))
        prio = _clean((policy or {}).get("transfer_priority")) or _clean(entry.get("transfer_priority"))
        info = _clean(entry.get("info_to_collect"))
        script = _clean(entry.get("transfer_script"))
        parts = [
            base_system,
            "\n\nSTRICT POLICY MODE — this is a security, policy, account, or data matter.",
            "You MUST NOT troubleshoot, improvise, guess, or invent any steps, contacts, or facts.",
            "Convey ONLY the following official guidance, naturally and briefly, in the caller's language:",
            f'"{verbatim}"' if verbatim else "(state that this must be handled by IT and cannot be done on the call)",
        ]
        if info:
            parts.append(f"Then collect exactly this information if the caller hasn't given it: {info}.")
        if prio or script:
            parts.append(f"Then escalate to a human ({prio}). Handoff approach: {script}".rstrip())
        parts.append("Do not say anything beyond this. Do not offer troubleshooting steps.")
        return "\n".join(p for p in parts if p)

    # LLM_ANSWERED — dynamic deep-dive, strictly grounded in KB steps.
    title = _clean(entry.get("title"))
    steps = _clean(entry.get("checklist_steps"))
    probes = _clean(entry.get("probing_questions"))
    mustnot = _clean(entry.get("policy_boundary"))
    maxs = entry.get("max_steps")
    prio = _clean(entry.get("transfer_priority"))
    trigger = _clean(entry.get("transfer_trigger"))
    script = _clean(entry.get("transfer_script"))
    info = _clean(entry.get("info_to_collect"))

    parts = [
        base_system,
        f"\n\nThe caller's issue matches: {title}." if title else "",
        "Troubleshoot dynamically, but stay STRICTLY grounded in the knowledge base below.",
        "Never invent steps, contacts, or facts that are not listed. Ask ONE step or question "
        "at a time, briefly, in the caller's language, and wait for their reply.",
    ]
    if probes:
        parts.append(f"Probing questions to narrow the cause: {probes}")
    if steps:
        parts.append(f"The ONLY fix steps you may use, in order: {steps}")
    if mustnot:
        parts.append(f"You must NEVER do any of these: {mustnot}")
    guard = "After "
    guard += f"at most {maxs} steps" if maxs else "the standard checks"
    if trigger:
        guard += f", or if this happens ({trigger}),"
    guard += " stop troubleshooting"
    if info:
        guard += f", collect: {info},"
    guard += f" and escalate to a human ({prio}). Handoff approach: {script}".rstrip()
    parts.append(guard + ".")
    return "\n".join(p for p in parts if p)