"""
Voice session endpoint.

POST /api/sessions/start  { agent_id }
  1. validates the agent exists & is active
  2. creates a LiveKit room name
  3. mints a browser token
  4. returns { room, url, token, agent_id }

The agent worker (worker/agent_worker.py) is dispatched to the same room (either
by LiveKit agent dispatch or by your own job runner) and fetches the agent config.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.agent import Agent
from backend.services.livekit_service import create_room_token, new_room_name

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class StartSessionRequest(BaseModel):
    agent_id: uuid.UUID
    user_identity: str | None = None


class StartSessionResponse(BaseModel):
    agent_id: uuid.UUID
    room: str
    url: str
    token: str


@router.post("/start", response_model=StartSessionResponse)
def start_session(payload: StartSessionRequest, db: Session = Depends(get_db)):
    agent = db.get(Agent, payload.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    if not agent.is_active:
        raise HTTPException(400, "Agent is inactive")

    room = new_room_name(agent.id)
    identity = payload.user_identity or f"user-{uuid.uuid4().hex[:8]}"
    token = create_room_token(identity, room, is_agent=False)

    # The room name encodes the agent id so the worker knows which config to load.
    return StartSessionResponse(
        agent_id=agent.id,
        room=room,
        url=settings.LIVEKIT_URL,
        token=token,
    )

class OutboundCallRequest(BaseModel):
    agent_id: uuid.UUID
    phone_number: str

@router.post("/outbound")
async def outbound_call(payload: OutboundCallRequest, db: Session = Depends(get_db)):
    import os
    from livekit import api as lk_api
    
    agent = db.get(Agent, payload.agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    if not agent.is_active:
        raise HTTPException(400, "Agent is inactive")

    room = new_room_name(agent.id)
    outbound_trunk_id = os.getenv("JIO_OUTBOUND_TRUNK_ID")
    if not outbound_trunk_id:
        raise HTTPException(500, "JIO_OUTBOUND_TRUNK_ID is not configured in .env")

    lk = lk_api.LiveKitAPI(
        url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET
    )
    
    try:
        phone = payload.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone

        await lk.sip.create_sip_participant(
            lk_api.CreateSIPParticipantRequest(
                sip_trunk_id=outbound_trunk_id,
                sip_call_to=phone,
                room_name=room,
                participant_identity=f"sip-{payload.phone_number}",
            )
        )
        return {"status": "success", "room": room, "message": f"Calling {phone}..."}
    except Exception as e:
        raise HTTPException(500, f"Failed to initiate outbound call: {e}")
    finally:
        await lk.aclose()
