"""
Sarvam v3 WebSocket client using official Sarvam SDK.

Reason:
Manual websocket payload was connecting but Sarvam returned:
422 - "Input parameters has to be a valid dictionary".

The official SDK test passed successfully, so this client delegates
configure/convert/flush protocol handling to Sarvam's SDK.
"""
from __future__ import annotations

import base64
import logging
from typing import AsyncIterator

from module.tts_core.providers.sarvam_v3.audio import coerce_to_pcm
from module.tts_core.providers.sarvam_v3.errors import SarvamV3TTSError

log = logging.getLogger("tts_core.sarvam_v3.ws")

_MODEL = "bulbul:v3"
_RECV_TIMEOUT = 30


def _extract_config(config_msg: dict) -> dict:
    """Accept old/new config shapes and convert them to SDK configure kwargs."""
    if not isinstance(config_msg, dict):
        return {}

    data = config_msg

    # Old docs-style envelope: {"type": "config", "data": {...}}
    if config_msg.get("type") == "config" and isinstance(config_msg.get("data"), dict):
        data = config_msg["data"]

    # Earlier experimental shape: {"input_params": {...}}
    if isinstance(data.get("input_params"), dict):
        data = data["input_params"]

    params = {
        "target_language_code": data.get("target_language_code", "en-IN"),
        "speaker": data.get("speaker", "shubh"),
        "pace": float(data.get("pace", 1.0)),
        "min_buffer_size": int(data.get("min_buffer_size", 50)),
        "max_chunk_length": int(data.get("max_chunk_length", 200)),
        "output_audio_codec": data.get("output_audio_codec", "linear16"),
    }

    codec = str(params["output_audio_codec"]).lower()
    if codec in {"mp3", "aac", "opus"}:
        params["output_audio_bitrate"] = data.get("output_audio_bitrate", "128k")

    return params


class SarvamV3WebSocketClient:
    """SDK-backed WebSocket client: configure, convert, flush, yield PCM."""

    def __init__(self, api_key: str, ws_url: str | None = None):
        self._api_key = api_key
        self._ws_url = ws_url  # kept for compatibility; SDK manages endpoint

    async def _import_sdk(self):
        try:
            from sarvamai import AsyncSarvamAI, AudioOutput, EventResponse
            return AsyncSarvamAI, AudioOutput, EventResponse
        except ImportError as exc:
            raise SarvamV3TTSError(
                "sarvamai package not installed. Add sarvamai==0.1.28 to worker requirements."
            ) from exc

    async def synthesize_stream(self, text: str, config_msg: dict, sample_rate: int) -> AsyncIterator[bytes]:
        AsyncSarvamAI, AudioOutput, EventResponse = await self._import_sdk()

        params = _extract_config(config_msg)
        client = AsyncSarvamAI(api_subscription_key=self._api_key)

        try:
            async with client.text_to_speech_streaming.connect(
                model=_MODEL,
                send_completion_event=True,
            ) as ws:
                log.info("WebSocket connected to Sarvam v3 TTS via official SDK")

                await ws.configure(**params)
                await ws.convert(text)
                await ws.flush()

                async for message in ws:
                    if isinstance(message, AudioOutput):
                        audio_b64 = message.data.audio
                        if audio_b64:
                            yield coerce_to_pcm(base64.b64decode(audio_b64), sample_rate)

                    elif isinstance(message, EventResponse):
                        event_type = getattr(message.data, "event_type", "")
                        if event_type == "final":
                            break

        except SarvamV3TTSError:
            raise
        except Exception as exc:
            log.error("Sarvam v3 SDK WS failed: %s", exc)
            log.error("Sarvam v3 SDK WS config that was used: %s", params)
            raise SarvamV3TTSError(f"Sarvam v3 SDK WS failed: {exc}") from exc
