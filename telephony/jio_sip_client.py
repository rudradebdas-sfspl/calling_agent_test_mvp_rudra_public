"""
jio_sip_client.py — Outbound call via JIO SIP trunk through LiveKit SIP

Uses LiveKit's create_sip_participant API to place outbound calls.
The call goes: LiveKit SIP → JIO SIP Trunk → PSTN number.
The LiveKit agent automatically joins the room and handles the conversation.

REQUIRES:
  JIO_OUTBOUND_TRUNK_ID — from setup_jio_sip.py output
  LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
"""

import os
import json
import asyncio
import logging
import time
from typing import Optional
from pathlib import Path
from urllib.parse import urlparse

from livekit import api

logger = logging.getLogger("telephony.jio_sip_client")


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# Configuration
LIVEKIT_URL        = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY    = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

JIO_SIP_HOST       = os.getenv("JIO_SIP_HOST", "")
JIO_SIP_USERNAME   = os.getenv("JIO_SIP_USERNAME", "")
JIO_SIP_PASSWORD   = os.getenv("JIO_SIP_PASSWORD", "")
JIO_DID_NUMBER     = os.getenv("JIO_DID_NUMBER", "")
JIO_OUTBOUND_TRUNK = os.getenv("JIO_OUTBOUND_TRUNK_ID", "")
JIO_OUTBOUND_CALLER_ID = os.getenv("JIO_OUTBOUND_CALLER_ID", "").strip()

MAX_RETRIES        = max(1, int(os.getenv("JIO_MAX_RETRIES", "1")))
RETRY_BACKOFF_BASE = float(os.getenv("JIO_RETRY_BACKOFF_BASE", "1.5"))
WAIT_UNTIL_ANSWERED = _env_bool("JIO_WAIT_UNTIL_ANSWERED", False)
TRY_ALL_LIVEKIT_URLS = _env_bool("JIO_TRY_ALL_LIVEKIT_URLS", False)
ENABLE_AGENT_DISPATCH = _env_bool("JIO_ENABLE_AGENT_DISPATCH", True)
AGENT_DISPATCH_RETRIES = max(1, int(os.getenv("JIO_AGENT_DISPATCH_RETRIES", "8")))
AGENT_DISPATCH_RETRY_SEC = max(0.20, float(os.getenv("JIO_AGENT_DISPATCH_RETRY_SEC", "0.8")))
LIVEKIT_AGENT_NAME = (os.getenv("LIVEKIT_AGENT_NAME", "collection-agent") or "collection-agent").strip()
# PBX-dependent dial format for outbound PSTN numbers.
SIP_DIAL_FORMAT    = os.getenv("SIP_DIAL_FORMAT", "zero_prefix").strip().lower()


def _runtime_livekit_url() -> str:
    return os.getenv("LIVEKIT_URL", "").strip() or LIVEKIT_URL


def _candidate_livekit_urls() -> list[str]:
    primary = _runtime_livekit_url()
    urls: list[str] = []

    def _add(url: str) -> None:
        u = (url or "").strip()
        if u and u not in urls:
            urls.append(u)

    _add(primary)

    # Explicit fallbacks for hosted environments where service DNS differs.
    # Example:
    #   LIVEKIT_URL_FALLBACKS=ws://localhost:7880,ws://127.0.0.1:7880
    raw_fallbacks = os.getenv("LIVEKIT_URL_FALLBACKS", "")
    for item in raw_fallbacks.split(","):
        _add(item)

    try:
        parsed = urlparse(primary)
        scheme = parsed.scheme or "ws"
        port = parsed.port or (443 if scheme == "wss" else 80)
        host = (parsed.hostname or "").lower()

        if host in {"livekit", "localhost", "127.0.0.1"}:
            _add(f"{scheme}://livekit:{port}")
            _add(f"{scheme}://localhost:{port}")
            _add(f"{scheme}://127.0.0.1:{port}")
            _add(f"{scheme}://host.docker.internal:{port}")

        public_host = (os.getenv("PUBLIC_HOSTNAME", "") or "").strip()
        if public_host and "<" not in public_host and "fill" not in public_host.lower():
            _add(f"{scheme}://{public_host}:{port}")

        public_domain = (os.getenv("PUBLIC_DOMAIN", "") or "").strip()
        if public_domain and "<" not in public_domain and "fill" not in public_domain.lower():
            _add(f"wss://{public_domain}")
            _add(f"ws://{public_domain}:{port}")
    except Exception:
        pass

    # Avoid duplicate dispatch attempts by default. Enable
    # JIO_TRY_ALL_LIVEKIT_URLS=true only when debugging URL reachability.
    if not TRY_ALL_LIVEKIT_URLS and urls:
        return [urls[0]]
    return urls


def _load_trunk_id_from_file() -> str:
    """Try to load outbound trunk ID from sip_trunk_ids.json if env is not set."""
    for path in [
        Path("sip_trunk_ids.json"),
        Path("/app/sip_trunk_ids.json"),
        Path(__file__).parent.parent.parent.parent / "sip_trunk_ids.json",
    ]:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                trunk_id = data.get("outbound_trunk_id", "")
                if trunk_id:
                    logger.info("Loaded outbound trunk ID from %s: %s", path, trunk_id)
                    return trunk_id
            except Exception as e:
                logger.warning("Could not read %s: %s", path, e)
    return ""


def _get_outbound_trunk_id() -> str:
    """Get the outbound trunk ID from env or file."""
    # Read runtime env first so trunk rotations are picked up immediately
    trunk_id = os.getenv("JIO_OUTBOUND_TRUNK_ID", "").strip() or JIO_OUTBOUND_TRUNK
    if not trunk_id:
        trunk_id = _load_trunk_id_from_file()
    return trunk_id


def _normalize_number(number: str) -> str:
    """Normalize phone number: strip '+', spaces, dashes. Ensure 91 prefix."""
    cleaned = number.strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    # Ensure Indian country code
    if len(cleaned) == 10 and cleaned[0] in "6789":
        cleaned = "91" + cleaned
    return cleaned


def _normalize_outbound_caller_id(value: str) -> str:
    """Normalize SIP caller identity while allowing extension-style usernames."""
    cleaned = value.strip().replace(" ", "").replace("-", "")
    if not cleaned:
        return ""
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.isdigit() and len(cleaned) == 10 and cleaned[0] in "6789":
        return "+91" + cleaned
    if cleaned.isdigit() and len(cleaned) == 12 and cleaned.startswith("91"):
        return "+" + cleaned
    return cleaned


def _apply_dial_format(normalized: str) -> str:
    """Apply PBX-required dial format based on SIP_DIAL_FORMAT env."""
    last10 = normalized[-10:]
    fmt = SIP_DIAL_FORMAT
    if fmt == "91_prefix":
        return "91" + last10
    if fmt == "raw10":
        return last10
    if fmt == "zero_prefix":
        return "0" + last10
    if fmt == "e164":
        return "+91" + last10
    if fmt == "nine_prefix":
        return "9" + last10
    # default
    return "91" + last10


class JioSIPClientError(Exception):
    """Raised when a JIO SIP call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _is_matching_outbound_trunk(trunk: object) -> bool:
    """Return True when a trunk matches the configured JIO outbound target host."""
    name = (getattr(trunk, "name", "") or "").lower()
    address = (getattr(trunk, "address", "") or "").lower()
    host = JIO_SIP_HOST.lower()
    my_host = os.getenv("MY_SIP_HOST", "").lower()
    if address and ((host and address.startswith(f"{host}:")) or (my_host and address.startswith(f"{my_host}:"))):
        return True
    # Keep legacy compatibility only when address is absent.
    return name == "jio-outbound" and not address


async def _resolve_outbound_trunk_id(
    lk: api.LiveKitAPI,
    preferred_trunk_id: str,
) -> str:
    """
    Resolve a usable outbound trunk ID.

    Priority:
      1) preferred ID from env/file if it exists in LiveKit
      2) existing trunk that matches JIO host/name
      3) create a new trunk and use it immediately
    """
    preferred_trunk_id = (preferred_trunk_id or "").strip()

    listed = await lk.sip.list_outbound_trunk(api.ListSIPOutboundTrunkRequest())
    trunks = list(listed.items or [])

    if preferred_trunk_id:
        for t in trunks:
            if getattr(t, "sip_trunk_id", "") == preferred_trunk_id:
                return preferred_trunk_id

    for t in trunks:
        if _is_matching_outbound_trunk(t):
            matched_id = getattr(t, "sip_trunk_id", "")
            if matched_id:
                if preferred_trunk_id and matched_id != preferred_trunk_id:
                    logger.warning(
                        "Configured trunk %s not found. Using available trunk %s instead.",
                        preferred_trunk_id, matched_id,
                    )
                return matched_id

    my_sip_host = os.getenv("MY_SIP_HOST", JIO_SIP_HOST)
    my_sip_port = os.getenv("MY_SIP_PORT", "5062")
    address = f"{my_sip_host}:{my_sip_port}"

    logger.warning(
        "No outbound trunk found in LiveKit. Creating a new jio-outbound trunk for %s.",
        address,
    )
    created = await lk.sip.create_outbound_trunk(
        api.CreateSIPOutboundTrunkRequest(
            trunk=api.SIPOutboundTrunkInfo(
                name="jio-outbound",
                address=address,
                numbers=["*"],
                auth_username=JIO_SIP_USERNAME,
                auth_password=JIO_SIP_PASSWORD,
            )
        )
    )
    new_id = getattr(created, "sip_trunk_id", "")
    if not new_id:
        raise JioSIPClientError("Created outbound trunk but did not receive a trunk ID")
    logger.info("Created new outbound trunk: %s", new_id)
    return new_id


async def _ensure_agent_dispatch(
    lk: api.LiveKitAPI,
    *,
    room_name: str,
    metadata: str = "",
) -> str:
    """
    Ensure explicit agent dispatch exists for the room.

    Why:
      SIP participant may be created while worker is recycling/not yet registered.
      Explicit dispatch with retries avoids "connected but silent" calls.
    """
    if not ENABLE_AGENT_DISPATCH:
        return ""

    # One quick check: explicit dispatch for our agent might already exist.
    try:
        existing = await lk.agent_dispatch.list_dispatch(room_name)
        if existing:
            for item in existing:
                existing_agent = str(getattr(item, "agent_name", "") or "").strip()
                dispatch_id = str(getattr(item, "id", "") or "")
                if existing_agent == LIVEKIT_AGENT_NAME and dispatch_id:
                    logger.info(
                        "JIO AGENT DISPATCH reuse | room=%s | agent=%s | dispatch_id=%s",
                        room_name, LIVEKIT_AGENT_NAME, dispatch_id,
                    )
                    return dispatch_id
    except Exception:
        pass

    last_err: Optional[Exception] = None
    for attempt in range(1, AGENT_DISPATCH_RETRIES + 1):
        try:
            created = await lk.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=LIVEKIT_AGENT_NAME,
                    room=room_name,
                    metadata=metadata or "",
                )
            )
            dispatch_id = str(getattr(created, "id", "") or "")
            logger.info(
                "JIO AGENT DISPATCH OK | room=%s | agent=%s | dispatch_id=%s | attempt=%d/%d",
                room_name, LIVEKIT_AGENT_NAME, dispatch_id or "n/a", attempt, AGENT_DISPATCH_RETRIES,
            )
            return dispatch_id
        except Exception as e:
            last_err = e
            logger.warning(
                "JIO AGENT DISPATCH retry | room=%s | agent=%s | attempt=%d/%d | err=%s",
                room_name, LIVEKIT_AGENT_NAME, attempt, AGENT_DISPATCH_RETRIES, e,
            )
            if attempt < AGENT_DISPATCH_RETRIES:
                await asyncio.sleep(AGENT_DISPATCH_RETRY_SEC)

    if last_err:
        logger.error(
            "JIO AGENT DISPATCH FAILED | room=%s | agent=%s | retries=%d | final_err=%s",
            room_name, LIVEKIT_AGENT_NAME, AGENT_DISPATCH_RETRIES, last_err,
        )
    return ""


async def make_outbound_call(
    to_number: str,
    custom_field: Optional[str] = None,
    callee_name: Optional[str] = None,
    callee_gender: Optional[str] = None,
    agent_id: Optional[int] = None,
    room_name: Optional[str] = None,
) -> dict:
    """
    Place an outbound call via JIO SIP trunk through LiveKit.

    Flow:
      1. Create a unique LiveKit room
      2. Create SIP participant that dials out via JIO trunk
      3. LiveKit agent auto-joins the room (via dispatch rule / worker)
      4. Conversation happens in the room

    Args:
        to_number: Target phone number (Indian mobile)
        custom_field: Optional tag for tracking

    Returns:
        dict with keys: call_sid, call_status, room_name, mode

    Raises:
        JioSIPClientError on failure.
    """
    trunk_id = _get_outbound_trunk_id()

    normalized_to = _normalize_number(to_number)
    if len(normalized_to) < 10:
        raise JioSIPClientError(f"Invalid phone number: {to_number}")

    # Create unique room name for this call, or use provided room_name
    if room_name is None:
        timestamp = int(time.time() * 1000)
        if agent_id is not None:
            room_name = f"agent-{agent_id}-jio-call-out-{normalized_to[-4:]}-{timestamp}"
        else:
            room_name = f"jio-call-out-{normalized_to[-4:]}-{timestamp}"

    # LiveKit wants just a phone number or SIP user in `sip_call_to`;
    # passing a full URI triggers a 400 error (see dashboard screenshot).  Keep
    # the URI around for debugging/logging but send the bare number.
    sip_uri = f"sip:{normalized_to}@{JIO_SIP_HOST}"
    sip_call_to = _apply_dial_format(normalized_to)
    sip_number = _normalize_outbound_caller_id(JIO_OUTBOUND_CALLER_ID)

    logger.info(
        "JIO SIP OUTBOUND | to=%s | dial_to=%s | caller=%s | room=%s | trunk=%s | uri=%s",
        normalized_to, sip_call_to, sip_number or "(trunk-default)", room_name, trunk_id or "auto", sip_uri,
    )

    # Retry loop
    livekit_urls = _candidate_livekit_urls()
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("LiveKit SIP attempt %d/%d", attempt, MAX_RETRIES)
        for lk_url in livekit_urls:
            try:
                lk = api.LiveKitAPI(
                    url=lk_url,
                    api_key=LIVEKIT_API_KEY,
                    api_secret=LIVEKIT_API_SECRET,
                )

                try:
                    effective_trunk_id = await _resolve_outbound_trunk_id(lk, trunk_id)
                    participant_info = await lk.sip.create_sip_participant(
                        api.CreateSIPParticipantRequest(
                            sip_trunk_id=effective_trunk_id,
                            sip_call_to=sip_call_to,
                            sip_number=sip_number,
                            room_name=room_name,
                            participant_identity=f"sip-caller-{normalized_to}",
                            participant_name=f"Call to {normalized_to}",
                            participant_metadata=json.dumps({
                                k: v for k, v in {
                                    "callee_name": callee_name,
                                    "callee_gender": callee_gender,
                                    "agent_id": agent_id,
                                }.items() if v is not None and v != ""
                            }) if (callee_name or callee_gender or agent_id is not None) else "",
                            dtmf="",
                            # Keep dispatch stable (no re-dial loops on slow answer) unless explicitly enabled.
                            wait_until_answered=WAIT_UNTIL_ANSWERED,
                            play_ringtone=False,
                            hide_phone_number=False,
                        )
                    )
                    dispatch_meta = json.dumps(
                        {
                            k: v
                            for k, v in {
                                "source": "jio_sip_outbound",
                                "room_name": room_name,
                                "phone_number": normalized_to,
                                "custom_field": custom_field,
                                "agent_id": agent_id,
                            }.items()
                            if v is not None and v != ""
                        }
                    )
                    dispatch_id = await _ensure_agent_dispatch(
                        lk,
                        room_name=room_name,
                        metadata=dispatch_meta,
                    )
                finally:
                    await lk.aclose()

                # Extract participant info
                participant_id = getattr(participant_info, "participant_id", "") or \
                                 getattr(participant_info, "sip_call_id", "") or \
                                 room_name

                logger.info(
                    "JIO SIP OUTBOUND OK | participant=%s | room=%s | livekit=%s",
                    participant_id, room_name, lk_url,
                )

                return {
                    "call_sid": participant_id,
                    "call_status": "dispatched",
                    "room_name": room_name,
                    "sip_uri": sip_uri,
                    "mode": "jio_sip_livekit",
                    "dispatch_id": dispatch_id or "",
                    "raw_response": str(participant_info),
                }

            except Exception as e:
                last_error = JioSIPClientError(f"LiveKit SIP error: {e}")
                logger.warning("Attempt %d via %s failed: %s", attempt, lk_url, e)
                err_text = str(e).lower()
                # If primary LiveKit replied with a SIP/Twirp error, localhost fallback
                # only hides the real cause in UI logs. Skip localhost in that case.
                if (
                    "localhost" not in lk_url
                    and ("sip status" in err_text or "twirperror" in err_text or "status=400" in err_text)
                ):
                    logger.warning(
                        "LiveKit reachable but SIP rejected the call; skipping localhost fallback for this attempt."
                    )
                    break

        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            logger.info("Retrying in %.1fs...", wait)
            await asyncio.sleep(wait)

    raise last_error or JioSIPClientError("All retry attempts failed")


async def dispatch_jio_inbound_call(
    caller_number: str,
    called_number: str,
    call_id: str,
    agent_id: int,
    agent_config: dict,
) -> dict:
    """
    Handle an inbound JIO SIP call by creating a LiveKit room and dispatching the agent.

    Args:
        caller_number: The caller's phone number (from JIO callback)
        called_number: The DID number that was called
        call_id: JIO SIP call ID for tracking
        agent_id: The agent ID to handle this call
        agent_config: Agent configuration from database

    Returns:
        dict with room_name, participant_id, and dispatch status
    """
    from app.database.db import insert_inbound_call_log

    normalized_caller = _normalize_number(caller_number)

    # Create unique room name
    timestamp = int(time.time() * 1000)
    room_name = f"jio-inbound-{agent_id}-{normalized_caller[-4:]}-{timestamp}"

    logger.warning(
        "[INBOUND_DISPATCH] START | caller=%s | agent=%s | call_id=%s | room=%s | livekit_url=%s",
        normalized_caller, agent_id, call_id, room_name, LIVEKIT_URL,
    )

    # Try to create participant in LiveKit
    livekit_urls = _candidate_livekit_urls()
    last_error = None

    for attempt in range(1, max(2, AGENT_DISPATCH_RETRIES // 2 + 1)):
        for lk_url in livekit_urls:
            try:
                lk = api.LiveKitAPI(
                    url=lk_url,
                    api_key=LIVEKIT_API_KEY,
                    api_secret=LIVEKIT_API_SECRET,
                )

                try:
                    # Dispatch agent to room
                    dispatch_meta = {
                        "agent_id": agent_id,
                        "caller": normalized_caller,
                        "called": called_number,
                        "jio_call_id": call_id,
                        "call_direction": "inbound",
                        **(agent_config.get("metadata") or {}),
                    }

                    logger.warning(f"[INBOUND_DISPATCH] Dispatching agent to room={room_name} with metadata={dispatch_meta}")

                    dispatch_id = await _ensure_agent_dispatch(
                        lk,
                        room_name=room_name,
                        metadata=json.dumps(dispatch_meta),
                    )

                    participant_id = f"jio-inbound-{call_id}"

                    logger.warning(
                        "[INBOUND_DISPATCH] Agent dispatched OK | participant=%s | room=%s | agent=%s | dispatch_id=%s",
                        participant_id, room_name, agent_id, dispatch_id,
                    )

                    # Log inbound call to database
                    try:
                        await insert_inbound_call_log(
                            room_name=room_name,
                            caller=normalized_caller,
                            called=called_number,
                            agent_id=agent_id,
                            jio_call_id=call_id,
                        )
                    except Exception as db_err:
                        logger.warning(f"Failed to log inbound call: {db_err}")

                    return {
                        "call_sid": participant_id,
                        "call_status": "dispatched",
                        "room_name": room_name,
                        "agent_id": agent_id,
                        "caller": normalized_caller,
                        "mode": "jio_sip_inbound",
                        "dispatch_id": dispatch_id or "",
                    }

                finally:
                    await lk.aclose()

            except Exception as e:
                last_error = JioSIPClientError(f"LiveKit inbound error: {e}")
                logger.warning("Inbound attempt %d via %s failed: %s", attempt, lk_url, e)

        if attempt < max(2, AGENT_DISPATCH_RETRIES // 2 + 1):
            await asyncio.sleep(AGENT_DISPATCH_RETRY_SEC)

    raise last_error or JioSIPClientError("Failed to dispatch inbound call to agent")
