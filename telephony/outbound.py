"""
outbound.py — JIO SIP outbound call initiation.
"""

import os
import logging
from typing import Optional

from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("telephony.outbound")


class OutboundCallRequest(BaseModel):
    to: str
    custom_field: Optional[str] = None


async def handle_outbound_call(body: OutboundCallRequest) -> JSONResponse:
    """Handle outbound call request via JIO SIP."""
    return await _handle_jio_sip_outbound(body)


# ── JIO SIP Mode ─────────────────────────────────────────────────────────────

async def _handle_jio_sip_outbound(body: OutboundCallRequest) -> JSONResponse:
    """Handle outbound call via JIO SIP through LiveKit."""
    from app.telephony.jio_sip_client import make_outbound_call, JioSIPClientError

    trunk_id = os.getenv("JIO_OUTBOUND_TRUNK_ID", "")
    livekit_url = os.getenv("LIVEKIT_URL", "")

    errors = []
    if not trunk_id:
        errors.append(
            "JIO_OUTBOUND_TRUNK_ID missing — run setup_jio_sip.py first "
            "and set JIO_OUTBOUND_TRUNK_ID in .env"
        )
    if not livekit_url:
        errors.append("LIVEKIT_URL missing from .env")

    if errors:
        return JSONResponse(
            status_code=400,
            content={"error": "Configuration incomplete", "details": errors},
        )

    to_num = body.to.strip().replace(" ", "").replace("-", "")
    logger.info("OUTBOUND JIO SIP | to=%s", to_num)

    try:
        result = await make_outbound_call(
            to_number=to_num,
            custom_field=body.custom_field,
        )
    except JioSIPClientError as e:
        logger.error("JIO SIP outbound error: %s", e)
        return JSONResponse(
            status_code=502,
            content={"error": f"JIO SIP call failed: {e}"},
        )

    logger.info(
        "OUTBOUND OK | call_sid=%s room=%s",
        result.get("call_sid"), result.get("room_name"),
    )

    return JSONResponse({
        "success":     True,
        "call_sid":    result["call_sid"],
        "call_status": result["call_status"],
        "room_name":   result.get("room_name", ""),
        "mode":        "jio_sip_livekit",
    })
