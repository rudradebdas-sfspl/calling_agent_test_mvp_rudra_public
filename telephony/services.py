"""
services.py
============
Service layer for JIO SIP outbound calls.
"""

import logging
from typing import Optional

from app.database.db import (
    get_call_logs,
    get_call_stats,
    insert_call_log,
    update_call_log,
)

logger = logging.getLogger("telephony.services")


async def dispatch_single_call(
    phone_number: str,
    custom_field: Optional[str] = None,
    batch_id: Optional[str] = None,
    name: Optional[str] = None,
    gender: Optional[str] = None,
    agent_id: Optional[int] = None,
    room_name: Optional[str] = None,
) -> dict:
    """
    Dispatch a single outbound call and log the result.
    """
    mode = "jio_sip"

    log_id = await insert_call_log(
        phone_number=phone_number,
        direction="outbound",
        status="initiated",
        batch_id=batch_id,
        name=name,
        gender=gender,
        provider=mode,
        agent_id=agent_id,
    )

    try:
        result = await _dispatch_jio_sip(
            phone_number,
            custom_field,
            batch_id,
            name,
            gender,
            agent_id,
            room_name,
        )

        initial_status = str(result.get("call_status") or "").strip().lower()
        if initial_status in {"", "unknown"}:
            initial_status = "dispatched"
        if initial_status == "answered":
            initial_status = "in-progress"
        if initial_status in {"queued", "initiated"}:
            initial_status = "dispatched"

        await update_call_log(
            log_id=log_id,
            status=initial_status,
            call_sid=result["call_sid"],
            room_name=result.get("room_name"),
        )
        return {
            "success": True,
            "call_sid": result["call_sid"],
            "call_status": result["call_status"],
            "room_name": result.get("room_name", ""),
            "log_id": log_id,
            "mode": result.get("mode", mode),
        }

    except Exception as e:
        logger.error("Call dispatch failed [%s] for %s: %s", mode, phone_number, e)
        await update_call_log(
            log_id=log_id,
            status="failed",
            error_message=str(e),
        )
        return {
            "success": False,
            "error": str(e),
            "log_id": log_id,
        }


async def _dispatch_jio_sip(
    phone_number: str,
    custom_field: Optional[str],
    batch_id: Optional[str],
    name: Optional[str],
    gender: Optional[str],
    agent_id: Optional[int],
    room_name: Optional[str] = None,
) -> dict:
    from app.telephony.jio_sip_client import make_outbound_call, JioSIPClientError
    try:
        return await make_outbound_call(
            to_number=phone_number,
            custom_field=custom_field or batch_id,
            callee_name=name,
            callee_gender=gender,
            agent_id=agent_id,
            room_name=room_name,
        )
    except JioSIPClientError:
        raise
    except Exception as e:
        raise JioSIPClientError(str(e))


async def fetch_call_logs(limit: int = 50, offset: int = 0, batch_id: Optional[str] = None) -> dict:
    logs = await get_call_logs(limit=limit, offset=offset, batch_id=batch_id)
    return {"logs": logs, "total": len(logs)}


async def fetch_call_stats() -> dict:
    return await get_call_stats()
