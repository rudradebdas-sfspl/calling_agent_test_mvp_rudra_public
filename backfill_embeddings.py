"""
Backfill embeddings for existing kb_chunks rows that don't have one yet.

Run AFTER `alembic upgrade head` (so the `embedding` column + pgvector exist):

    python backfill_embeddings.py            # embed all NULL-embedding rows
    python backfill_embeddings.py --agent <agent_uuid>   # only one agent
    python backfill_embeddings.py --reembed  # re-embed ALL rows (overwrite)

Safe to re-run: it only touches rows where embedding IS NULL unless --reembed.
"""
import argparse
import asyncio
import logging

from sqlalchemy import text

from backend.database import SessionLocal
from backend.services.embeddings import embed_texts, to_pgvector_literal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill")

BATCH = 64  # rows per DB fetch/embed loop


async def main(agent_id: str | None, reembed: bool) -> None:
    db = SessionLocal()
    try:
        where = "TRUE" if reembed else "embedding IS NULL"
        params: dict = {}
        if agent_id:
            where += " AND agent_id = CAST(:aid AS UUID)"
            params["aid"] = agent_id

        total = db.execute(
            text(f"SELECT COUNT(*) FROM kb_chunks WHERE {where}"), params
        ).scalar_one()
        log.info("Rows to embed: %d", total)
        if total == 0:
            return

        done = 0
        while True:
            rows = db.execute(
                text(f"""
                    SELECT id, content FROM kb_chunks
                    WHERE {where}
                    ORDER BY created_at
                    LIMIT :lim
                """),
                {**params, "lim": BATCH},
            ).fetchall()
            if not rows:
                break

            ids = [r[0] for r in rows]
            contents = [r[1] or "" for r in rows]
            vectors = await embed_texts(contents, task_type="RETRIEVAL_DOCUMENT")

            for row_id, vec in zip(ids, vectors):
                db.execute(
                    text("""
                        UPDATE kb_chunks
                        SET embedding = CAST(:vec AS halfvec)
                        WHERE id = :id
                    """),
                    {"vec": to_pgvector_literal(vec), "id": row_id},
                )
            db.commit()

            done += len(rows)
            log.info("Embedded %d / %d", done, total)

            # When --reembed, the WHERE (TRUE) never shrinks, so stop once we've
            # covered the initial total to avoid looping forever.
            if reembed and done >= total:
                break

        log.info("Done. Embedded %d rows.", done)
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default=None, help="only backfill this agent_id (UUID)")
    ap.add_argument("--reembed", action="store_true", help="re-embed ALL rows, overwriting existing vectors")
    args = ap.parse_args()
    asyncio.run(main(args.agent, args.reembed))