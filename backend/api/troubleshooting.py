"""
Troubleshooting KB endpoints — upload the structured IT troubleshooting Excel,
which populates kb_entries + policy_rules (with embeddings) for an agent.

Separate router (prefix .../troubleshooting) so it never collides with the
generic document KB routes under .../kb/{filename}.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.agent import Agent
from backend.services.troubleshooting_ingest import ingest_workbook

router = APIRouter(prefix="/api/agents/{agent_id}/troubleshooting", tags=["troubleshooting"])
log = logging.getLogger("troubleshooting_api")

_XLSX = (".xlsx", ".xlsm")


def _get_agent_or_404(agent_id: uuid.UUID, db: Session) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("")
def summary(agent_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return how many entries/policies are loaded + the KB-Fetch/LLM breakdown."""
    _get_agent_or_404(agent_id, db)
    aid = str(agent_id)
    entries = db.execute(
        text("SELECT count(*) FROM kb_entries WHERE agent_id = CAST(:a AS UUID)"), {"a": aid}
    ).scalar_one()
    policies = db.execute(
        text("SELECT count(*) FROM policy_rules WHERE agent_id = CAST(:a AS UUID)"), {"a": aid}
    ).scalar_one()
    breakdown = dict(
        db.execute(
            text("""SELECT answer_mode, count(*) FROM kb_entries
                    WHERE agent_id = CAST(:a AS UUID) GROUP BY answer_mode"""),
            {"a": aid},
        ).fetchall()
    )
    return {"entries": entries, "policies": policies, "by_answer_mode": breakdown}


@router.post("", status_code=201)
async def upload(
    agent_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload the troubleshooting .xlsx. Replaces any previous ingestion for this agent."""
    _get_agent_or_404(agent_id, db)
    fname = (file.filename or "").lower()
    if not fname.endswith(_XLSX):
        raise HTTPException(status_code=422, detail="Please upload an .xlsx file.")

    data = await file.read()
    try:
        result = await ingest_workbook(agent_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        log.exception("troubleshooting ingest failed")
        raise HTTPException(status_code=500, detail=f"Ingest failed: {exc}")

    return {"status": "ok", **result}


@router.delete("", status_code=204)
def clear(agent_id: uuid.UUID, db: Session = Depends(get_db)):
    """Remove all troubleshooting entries + policy rules for this agent."""
    _get_agent_or_404(agent_id, db)
    aid = str(agent_id)
    db.execute(text("DELETE FROM kb_entries WHERE agent_id = CAST(:a AS UUID)"), {"a": aid})
    db.execute(text("DELETE FROM policy_rules WHERE agent_id = CAST(:a AS UUID)"), {"a": aid})
    db.commit()