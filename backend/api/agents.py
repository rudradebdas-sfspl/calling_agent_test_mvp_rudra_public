"""Agent Builder CRUD endpoints. Persists the full runtime config to PostgreSQL."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.agent import Agent
from backend.schemas.agent import AgentCreate, AgentRead, AgentUpdate
from backend.services.vad.presets import PRESET_NOTES, PRESETS, VAD_MODES

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/vad-presets")
def list_vad_presets():
    """Exposes preset values + notes so the frontend can show them (no secrets)."""
    out = {}
    for mode in VAD_MODES:
        if mode in PRESETS:
            p = PRESETS[mode]
            out[mode] = {
                "threshold": p.threshold,
                "min_speech_ms": p.min_speech_ms,
                "min_silence_ms": p.min_silence_ms,
                "speech_pad_ms": p.speech_pad_ms,
                "note": PRESET_NOTES[mode],
            }
        else:
            out[mode] = {"note": PRESET_NOTES[mode]}
    return out


@router.get("", response_model=list[AgentRead])
def list_agents(db: Session = Depends(get_db)):
    return db.execute(select(Agent)).scalars().all()


@router.post("", response_model=AgentRead, status_code=201)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    agent = Agent(**payload.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: uuid.UUID, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: uuid.UUID, payload: AgentUpdate, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    for key, value in payload.model_dump().items():
        setattr(agent, key, value)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: uuid.UUID, db: Session = Depends(get_db)):
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    db.delete(agent)
    db.commit()


@router.post("/{agent_id}/set-sip-default", response_model=AgentRead)
def set_sip_default(agent_id: uuid.UUID, db: Session = Depends(get_db)):
    """Mark this agent as the default for inbound SIP/telephony calls.
    Clears is_sip_default on all other agents first (only one default at a time)."""
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    # Clear existing default
    db.execute(
        select(Agent).where(Agent.is_sip_default == True)  # noqa: E712
    ).scalars().all()
    for a in db.execute(select(Agent)).scalars().all():
        a.is_sip_default = False
    agent.is_sip_default = True
    db.commit()
    db.refresh(agent)
    return agent
