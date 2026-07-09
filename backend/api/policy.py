"""
Custom policy-rule endpoints — let a manager add guardrail/policy rules from the
frontend (as JSON), without editing the Excel. Each rule is embedded and stored
in the same `policy_rules` table the router already reads, so a newly added rule
takes effect on the next call.

Routes (prefix = /api/agents/{agent_id}/policy):
  GET    ""          -> list this agent's policy rules
  POST   ""          -> add one rule (JSON body)  [also embeds a matching kb_entries row]
  DELETE "/{rule_id}" -> remove one rule
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.agent import Agent
from backend.services.embeddings import embed_texts, to_pgvector_literal

router = APIRouter(prefix="/api/agents/{agent_id}/policy", tags=["policy"])
log = logging.getLogger("policy_api")


class PolicyRuleIn(BaseModel):
    rule_id: str | None = Field(default=None, description="Optional; auto-generated if blank")
    policy_area: str = Field(min_length=1)
    keywords: str = Field(default="", description="Trigger phrases callers might say")
    agent_says: str = Field(min_length=1, description="Verbatim line the agent must speak")
    answer_mode: str = Field(default="KB-Fetch Only")
    transfer_priority: str = Field(default="P2")


def _get_agent_or_404(agent_id: uuid.UUID, db: Session) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _canonical_mode(v: str) -> str:
    return "KB-Fetch Only" if "fetch" in (v or "").lower() else "LLM-Answered"


@router.get("")
def list_rules(agent_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_agent_or_404(agent_id, db)
    rows = db.execute(
        text("""SELECT rule_id, policy_area, agent_says, answer_mode, transfer_priority
                FROM policy_rules WHERE agent_id = CAST(:a AS UUID)
                ORDER BY rule_id"""),
        {"a": str(agent_id)},
    ).mappings().all()
    return {"rules": [dict(r) for r in rows]}


@router.post("", status_code=201)
async def add_rule(
    agent_id: uuid.UUID,
    body: PolicyRuleIn,
    db: Session = Depends(get_db),
):
    _get_agent_or_404(agent_id, db)
    aid = str(agent_id)

    # Resolve a rule_id (auto-generate a unique POL-CUSTOM-NN if not supplied).
    rule_id = (body.rule_id or "").strip()
    if not rule_id:
        n = db.execute(
            text("""SELECT count(*) FROM policy_rules
                    WHERE agent_id = CAST(:a AS UUID) AND rule_id LIKE 'POL-CUSTOM-%'"""),
            {"a": aid},
        ).scalar_one()
        rule_id = f"POL-CUSTOM-{n + 1:02d}"

    mode = _canonical_mode(body.answer_mode)

    # Text used for retrieval: keywords + policy area + the spoken line, so both
    # caller phrasings and the topic match well.
    content = "\n".join(p for p in [body.keywords, body.policy_area, body.agent_says] if p)
    try:
        vec = (await embed_texts([content], task_type="RETRIEVAL_DOCUMENT"))[0]
    except Exception as exc:
        log.exception("embedding failed for custom policy")
        raise HTTPException(status_code=500, detail=f"Embedding failed: {exc}")
    lit = to_pgvector_literal(vec)

    # Upsert-ish: replace an existing rule with the same rule_id for this agent.
    db.execute(
        text("""DELETE FROM policy_rules WHERE agent_id = CAST(:a AS UUID) AND rule_id = :rid"""),
        {"a": aid, "rid": rule_id},
    )
    db.execute(
        text("""
            INSERT INTO policy_rules
              (agent_id, rule_id, policy_area, rule_statement, agent_says,
               answer_mode, applies_to, transfer_priority, owner, content, embedding)
            VALUES
              (CAST(:a AS UUID), :rid, :area, :stmt, :says,
               :mode, :applies, :prio, :owner, :content, CAST(:emb AS halfvec))
        """),
        {
            "a": aid, "rid": rule_id, "area": body.policy_area,
            "stmt": body.policy_area, "says": body.agent_says, "mode": mode,
            "applies": body.keywords, "prio": body.transfer_priority,
            "owner": "Manager (UI)", "content": content, "emb": lit,
        },
    )

    # Also add a matching kb_entries row so the router (which searches kb_entries
    # first) can find this topic and pick up policy_rule_ref -> this rule.
    entry_id = f"KB-{rule_id}"
    db.execute(
        text("""DELETE FROM kb_entries WHERE agent_id = CAST(:a AS UUID) AND entry_id = :eid"""),
        {"a": aid, "eid": entry_id},
    )
    db.execute(
        text("""
            INSERT INTO kb_entries
              (agent_id, entry_id, category, title, description, keywords,
               answer_mode, transfer_priority, policy_rule_ref, content, embedding)
            VALUES
              (CAST(:a AS UUID), :eid, :cat, :title, :desc, :kw,
               :mode, :prio, :ref, :content, CAST(:emb AS halfvec))
        """),
        {
            "a": aid, "eid": entry_id, "cat": "Policy (custom)",
            "title": body.policy_area, "desc": body.agent_says, "kw": body.keywords,
            "mode": mode, "prio": body.transfer_priority, "ref": rule_id,
            "content": content, "emb": lit,
        },
    )

    db.commit()
    log.info("Added custom policy %s for agent %s", rule_id, aid)
    return {"status": "ok", "rule_id": rule_id, "answer_mode": mode}


@router.delete("/{rule_id}", status_code=204)
def delete_rule(agent_id: uuid.UUID, rule_id: str, db: Session = Depends(get_db)):
    _get_agent_or_404(agent_id, db)
    aid = str(agent_id)
    db.execute(
        text("DELETE FROM policy_rules WHERE agent_id = CAST(:a AS UUID) AND rule_id = :rid"),
        {"a": aid, "rid": rule_id},
    )
    db.execute(
        text("DELETE FROM kb_entries WHERE agent_id = CAST(:a AS UUID) AND entry_id = :eid"),
        {"a": aid, "eid": f"KB-{rule_id}"},
    )
    db.commit()
