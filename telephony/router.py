"""
router.py — Telephony routes (JIO SIP only).

KEY ENDPOINTS:
  /telephony-mode    — GET  current mode
  /switch-mode       — POST compatibility endpoint (mode stays jio_sip)
  /call              — Dispatch single outbound call
  /outbound-call     — Direct outbound call
  /batch-call        — Batch calls via Excel upload
  /batch-progress    — Real-time batch progress
  /call-logs         — Call log history
  /call-stats        — Call statistics
  /status-callback   — Call status updates
  /ping              — Reachability check
  /health            — Detailed health check
  /setup             — Setup guide page
"""

import json
import os
import logging
from urllib.parse import parse_qsl
from fastapi import APIRouter, Request, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, Response
from typing import Optional, Any
from pydantic import BaseModel

from app.core.config import get_telephony_mode, set_telephony_mode
from app.telephony.outbound import handle_outbound_call, OutboundCallRequest
from app.telephony.schemas import SingleCallRequest, SingleCallResponse, BatchCallResponse
from app.telephony.services import dispatch_single_call, fetch_call_logs, fetch_call_stats
from app.telephony.batch import prepare_batch, run_batch_background, get_batch_progress
from app.database.db import update_call_status_by_sid, update_call_media

logger = logging.getLogger("telephony.router")
router = APIRouter()


def _server_base(request: Request) -> str:
    pd = os.getenv("PUBLIC_DOMAIN", "") or os.getenv("PUBLIC_HOSTNAME", "")
    pd_ok = pd and "<" not in pd and "FILL" not in pd.upper()
    if pd_ok:
        return f"https://{pd}"
    host = request.headers.get("host", "localhost:8000")
    scheme = request.headers.get("x-forwarded-proto", "http")
    return f"{scheme}://{host}"


def _safe_int(raw: Any) -> Optional[int]:
    if raw in (None, "", "?"):
        return None
    try:
        return int(str(raw).strip())
    except (ValueError, TypeError):
        return None


async def _extract_callback_payload(request: Request) -> dict[str, Any]:
    payload: dict[str, Any] = dict(request.query_params)

    if request.method == "GET":
        return payload

    content_type = (request.headers.get("content-type", "") or "").lower()

    if "application/json" in content_type:
        try:
            body_json = await request.json()
            if isinstance(body_json, dict):
                payload.update(body_json)
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            payload.update(dict(form))
        except Exception:
            pass

    # Some providers send x-www-form-urlencoded but content-type may be missing/wrong.
    if len(payload) <= len(request.query_params):
        try:
            raw = (await request.body()).decode("utf-8", errors="ignore").strip()
            if raw:
                payload.update(dict(parse_qsl(raw, keep_blank_values=True)))
        except Exception:
            pass

    # Flatten nested call object if present.
    nested = payload.get("Call") or payload.get("call")
    nested_dict: dict[str, Any] = {}
    if isinstance(nested, dict):
        nested_dict = nested
    elif isinstance(nested, str):
        try:
            parsed = json.loads(nested)
            if isinstance(parsed, dict):
                nested_dict = parsed
        except Exception:
            nested_dict = {}
    for key, value in nested_dict.items():
        payload.setdefault(key, value)

    return payload


# ══════════════════════════════════════════════════════════════
#  MODE SWITCH — the main new feature
# ══════════════════════════════════════════════════════════════

class SwitchModeRequest(BaseModel):
    mode: str


@router.get("/telephony-mode")
async def telephony_mode():
    """Return current telephony mode + config status for dashboard."""
    mode = get_telephony_mode()
    config_ok = all([
        os.getenv("LIVEKIT_URL"),
        os.getenv("LIVEKIT_API_KEY"),
        os.getenv("LIVEKIT_API_SECRET"),
        os.getenv("JIO_SIP_HOST"),
        os.getenv("JIO_DID_NUMBER"),
    ])
    trunk_set = bool(os.getenv("JIO_OUTBOUND_TRUNK_ID", ""))

    return {
        "mode": mode,
        "config_ok": config_ok,
        "outbound_ready": config_ok and trunk_set,
        "jio_sip_host": os.getenv("JIO_SIP_HOST", ""),
        "jio_did": os.getenv("JIO_DID_NUMBER", ""),
    }


@router.post("/switch-mode")
async def switch_mode(body: SwitchModeRequest):
    """
    Compatibility endpoint for older dashboards.
    The stack stays pinned to JIO SIP.
    """
    old_mode = get_telephony_mode()
    new_mode = set_telephony_mode(body.mode)
    logger.info("TELEPHONY MODE SWITCHED: %s → %s", old_mode, new_mode)
    return {
        "success": True,
        "previous_mode": old_mode,
        "current_mode": new_mode,
        "message": "Telephony is locked to JIO SIP. New calls will keep using LiveKit SIP.",
    }


# ══════════════════════════════════════════════════════════════
#  CORE CALL ENDPOINTS
# ══════════════════════════════════════════════════════════════

@router.get("/ping")
async def ping():
    mode = get_telephony_mode()
    return {
        "status": "ok",
        "message": f"Telephony server is reachable — mode: {mode}",
        "mode": mode,
    }


@router.post("/outbound-call")
async def outbound_call(body: OutboundCallRequest):
    return await handle_outbound_call(body)


@router.post("/call", response_model=SingleCallResponse)
async def single_call(body: SingleCallRequest):
    result = await dispatch_single_call(
        phone_number=body.phone_number,
        custom_field=body.custom_field,
        name=body.name,
        gender=body.gender,
        agent_id=body.agent_id,
    )
    if result["success"]:
        return SingleCallResponse(
            success=True,
            message=f"Dispatched to {body.phone_number} via JIO SIP",
            call_sid=result.get("call_sid"),
            call_status=result.get("call_status"),
            log_id=result.get("log_id"),
        )
    return SingleCallResponse(
        success=False,
        message=result.get("error", "Failed"),
        log_id=result.get("log_id"),
    )


# ══════════════════════════════════════════════════════════════
#  BATCH CALLS
# ══════════════════════════════════════════════════════════════

@router.post("/batch-call", response_model=BatchCallResponse)
async def batch_call(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    agent_id: Optional[int] = Form(None),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        return JSONResponse(
            status_code=400, content={"success": False, "message": "Only .xlsx accepted"}
        )
    try:
        file_bytes = await file.read()
        result = prepare_batch(file_bytes)
        validated = result.get("validated", [])
        if not validated:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "No valid phone numbers found"},
            )
        background_tasks.add_task(run_batch_background, result["batch_id"], validated, agent_id)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    total_valid = len(validated)
    total_invalid = len(result.get("errors", []))
    return BatchCallResponse(
        success=True,
        message=(
            f"Batch queued: {total_valid} calls via JIO SIP. "
            f"{total_invalid} invalid skipped. "
            f"Track: /batch-progress/{result['batch_id']}"
        ),
        batch_id=result["batch_id"],
        total=result["total"],
        dispatched=0,
        failed=total_invalid,
        errors=result.get("errors", []),
    )


@router.get("/batch-progress/{batch_id}")
async def batch_progress(batch_id: str):
    progress = get_batch_progress(batch_id)
    if progress is None:
        return JSONResponse(status_code=404, content={"error": "Batch not found"})
    return progress


@router.get("/call-logs")
async def call_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    batch_id: Optional[str] = Query(None),
):
    return await fetch_call_logs(limit=limit, offset=offset, batch_id=batch_id)


@router.get("/call-stats")
async def call_stats():
    return await fetch_call_stats()


# ══════════════════════════════════════════════════════════════
#  STATUS CALLBACK
# ══════════════════════════════════════════════════════════════

@router.api_route("/status-callback", methods=["GET", "POST"])
async def status_callback(request: Request):
    try:
        d = await _extract_callback_payload(request)
        sid = (
            d.get("CallSid")
            or d.get("callSid")
            or d.get("callsid")
            or d.get("call_sid")
            or d.get("Call[Sid]")
            or d.get("Sid")
            or d.get("sid")
            or "?"
        )
        sid = str(sid).strip()
        status = (
            d.get("Status")
            or d.get("status")
            or d.get("CallStatus")
            or d.get("callStatus")
            or d.get("call_status")
            or d.get("Call[Status]")
            or "?"
        )
        status = str(status).strip()
        duration_raw = (
            d.get("Duration")
            or d.get("duration")
            or d.get("DialCallDuration")
            or d.get("dialCallDuration")
            or d.get("dial_call_duration")
            or d.get("Call[Duration]")
            or "?"
        )
        recording_url = (
            d.get("RecordingUrl")
            or d.get("recordingUrl")
            or d.get("recording_url")
            or d.get("CallRecordingUrl")
            or d.get("callRecordingUrl")
            or d.get("recording_url_0")
            or d.get("RecordingUrl0")
            or d.get("RecordingUrl_0")
            or d.get("Call[RecordingUrl]")
        )
        recording_sid = (
            d.get("RecordingSid")
            or d.get("recordingSid")
            or d.get("recording_sid")
            or d.get("CallRecordingSid")
            or d.get("callRecordingSid")
            or d.get("RecordingSid_0")
            or d.get("Call[RecordingSid]")
        )
        logger.info("STATUS CALLBACK | sid=%s status=%s duration=%s", sid, status, duration_raw)

        if sid and sid != "?":
            duration_int = _safe_int(duration_raw)

            status_map = {
                "completed": "completed",
                "failed": "failed",
                "busy": "failed",
                "no-answer": "failed",
                "no answer": "failed",
                "not-answered": "failed",
                "not answered": "failed",
                "canceled": "failed",
                "cancelled": "failed",
                "hangup": "completed",
                "disconnected": "completed",
                "answered": "in-progress",
                "in-progress": "in-progress",
                "ringing": "ringing",
                "queued": "initiated",
            }
            mapped = status_map.get(status.lower(), status.lower()) if status != "?" else None
            if mapped:
                updated = await update_call_status_by_sid(
                    call_sid=sid,
                    status=mapped,
                    duration=duration_int,
                    recording_url=recording_url,
                    recording_sid=recording_sid,
                )
                if not updated:
                    logger.warning(
                        "STATUS CALLBACK unmatched SID: sid=%s mapped=%s payload_keys=%s",
                        sid,
                        mapped,
                        sorted(list(d.keys())),
                    )
            elif recording_url or recording_sid:
                await update_call_media(
                    call_sid=sid,
                    recording_url=recording_url,
                    recording_sid=recording_sid,
                )

    except Exception as e:
        logger.warning("status-callback parse error: %s", e)
    return JSONResponse({"ok": True})


# ══════════════════════════════════════════════════════════════
#  JIO SIP INBOUND CALL HANDLER
# ══════════════════════════════════════════════════════════════

@router.api_route("/jio/incoming", methods=["GET", "POST"])
async def jio_incoming_call(request: Request):
    """
    Webhook endpoint for incoming JIO SIP calls.
    Returns SIP/VOIP XML instructions to route call to LiveKit.
    """
    try:
        import uuid
        from app.services.inbound_agent_state import get_inbound_agent_id
        from app.database.agent_registry import get_agent

        d = await _extract_callback_payload(request)

        # Extract caller info from JIO callback
        caller = d.get("caller") or d.get("from") or d.get("From") or d.get("CallFrom") or "Unknown"
        called = d.get("called") or d.get("to") or d.get("To") or d.get("CallTo") or os.getenv("JIO_DID_NUMBER", "")
        call_id = d.get("call_id") or d.get("callid") or d.get("CallID") or d.get("Sid") or str(uuid.uuid4())

        logger.warning(f"[JIO_INBOUND] WEBHOOK RECEIVED | caller={caller} called={called} call_id={call_id} payload_keys={list(d.keys())}")

        # Get the configured inbound agent
        agent_id = get_inbound_agent_id()
        if not agent_id:
            logger.warning("[JIO_INBOUND] No agent configured, rejecting call from %s", caller)
            return JSONResponse(status_code=403, content={"error": "No agent configured"})

        try:
            agent = await get_agent(agent_id)
            if not agent:
                logger.warning(f"[JIO_INBOUND] Agent {agent_id} not found")
                return JSONResponse(status_code=404, content={"error": "Agent not found"})
        except Exception as e:
            logger.warning(f"[JIO_INBOUND] Agent fetch error: {e}")
            return JSONResponse(status_code=500, content={"error": f"Agent fetch failed: {str(e)}"})

        # Dispatch to LiveKit and get room name
        try:
            from app.telephony.jio_sip_client import dispatch_jio_inbound_call

            result = await dispatch_jio_inbound_call(
                caller_number=caller,
                called_number=called,
                call_id=call_id,
                agent_id=agent_id,
                agent_config=agent,
            )
            room_name = result.get("room_name")
            logger.info(f"[JIO_INBOUND] Dispatched to LiveKit room: {room_name}")

        except Exception as e:
            logger.error(f"[JIO_INBOUND] Dispatch error: {e}", exc_info=True)
            return JSONResponse(status_code=500, content={"error": str(e)})

        # Return VoiceXML/SIP instructions to JIO to connect call to LiveKit SIP
        livekit_sip_host = os.getenv("LIVEKIT_SIP_HOST", "127.0.0.1")
        livekit_sip_port = os.getenv("LIVEKIT_SIP_PORT", "5060")

        # SIP dial target: sip:<room>@<livekit_sip_host>:<port>
        sip_dial_target = f"sip:{room_name}@{livekit_sip_host}:{livekit_sip_port}"

        logger.info(f"[JIO_INBOUND] Returning dial target: {sip_dial_target}")

        # Return VoiceML XML (format may vary by JIO version)
        voiceml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Dial>
    <SIP>{sip_dial_target}</SIP>
  </Dial>
</Response>"""

        return Response(content=voiceml, media_type="application/xml")

    except Exception as e:
        logger.error(f"[JIO_INBOUND] Handler error: {e}", exc_info=True)
        error_response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>An error occurred processing this call.</Say>
  <Hangup/>
</Response>"""
        return Response(content=error_response, media_type="application/xml")


# ══════════════════════════════════════════════════════════════
#  HEALTH CHECK & SETUP GUIDE
# ══════════════════════════════════════════════════════════════

@router.get("/health")
async def health(request: Request):
    base = _server_base(request)
    mode = get_telephony_mode()
    checks = {
        "LIVEKIT_URL":           bool(os.getenv("LIVEKIT_URL")),
        "LIVEKIT_API_KEY":       bool(os.getenv("LIVEKIT_API_KEY")),
        "LIVEKIT_API_SECRET":    bool(os.getenv("LIVEKIT_API_SECRET")),
        "JIO_SIP_HOST":          bool(os.getenv("JIO_SIP_HOST")),
        "JIO_DID_NUMBER":        bool(os.getenv("JIO_DID_NUMBER")),
        "JIO_OUTBOUND_TRUNK_ID": bool(os.getenv("JIO_OUTBOUND_TRUNK_ID")),
        "SARVAM_API_KEY":        bool(os.getenv("SARVAM_API_KEY")),
        "SARVAM_LLM_MODEL":      bool(os.getenv("SARVAM_LLM_MODEL", "sarvam-30b")),
        "GOOGLE_API_KEY_FOR_EMBEDDINGS": bool(os.getenv("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY"))),
    }

    missing = [k for k, v in checks.items() if not v]
    return JSONResponse(
        status_code=200 if not missing else 206,
        content={
            "status": "running",
            "mode": mode,
            "all_ok": not missing,
            "missing": missing,
            "detected_base": base,
            "env_check": {k: ("ok" if v else "MISSING") for k, v in checks.items()},
        },
    )


@router.get("/setup", response_class=HTMLResponse)
async def setup_guide(request: Request):
    base = _server_base(request)
    mode = get_telephony_mode()
    mode_display = "JIO SIP via LiveKit"

    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><title>BABA Setup</title><meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; }}
  .badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; color: #fff;
            background: {'#1976d2' if mode == 'jio_sip' else '#e65100'}; font-weight: bold; }}
</style></head><body>
<h1>BABA Voicebot Setup</h1>
<p>Server: <code>{base}</code></p>
<p>Active Mode: <span class="badge">{mode_display}</span></p>
<p>Outbound calling is configured for JIO SIP only.</p>
<pre>curl -X POST {base}/telephony/switch-mode \\
  -H "Content-Type: application/json" \\
  -d '{{"mode": "jio_sip"}}'</pre>
<h2>Endpoints</h2>
<ul>
  <li><code>GET  /telephony/ping</code> — health ping</li>
  <li><code>GET  /telephony/telephony-mode</code> — current mode</li>
  <li><code>POST /telephony/call</code> — single call</li>
  <li><code>POST /telephony/batch-call</code> — batch call</li>
  <li><code>GET  /telephony/call-logs</code> — logs</li>
  <li><code>GET  /telephony/health</code> — detailed health</li>
</ul>
</body></html>""")
