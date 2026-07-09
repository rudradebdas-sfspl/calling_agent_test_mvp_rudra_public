"""
LiveKit helper: mints access tokens for the browser and (optionally) ensures a
room exists. Keys come from env only.
"""
import uuid

from backend.config import settings


def create_room_token(identity: str, room_name: str, *, is_agent: bool = False) -> str:
    """
    Returns a signed LiveKit JWT for `identity` to join `room_name`.
    SDK: pip install livekit-api
    """
    from livekit import api

    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
    )
    token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("agent-worker" if is_agent else identity)
        .with_grants(grants)
        .to_jwt()
    )
    return token


def new_room_name(agent_id) -> str:
    return f"agent-{agent_id}-{uuid.uuid4().hex[:8]}"
