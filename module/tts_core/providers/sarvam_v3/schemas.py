"""
Sarvam Bulbul v3 request builders.

Model hardcoded: "bulbul:v3". No pitch/loudness/enable_preprocessing — v3
doesn't support them, and sending them causes the API to reject the request.

Builds payloads for:
  - REST  (/text-to-speech)   → build_tts_body()
  - WebSocket                  → build_ws_config() (consumed by ws_client.py,
    which passes these as kwargs to the official sarvamai SDK's
    ws.configure() — "model" is NOT included here because the SDK takes it
    separately, at client.text_to_speech_streaming.connect(model=...)).
"""
from __future__ import annotations

from module.tts_core.base import TTSConfig
from module.tts_core.providers.sarvam_v3.mapper import (
    clamp_pace, clamp_temperature, resolve_speaker, target_language, DEFAULT_TEMPERATURE,
)

_MODEL = "bulbul:v3"


# ── REST ──────────────────────────────────────────────────────────────────
def build_tts_body(text: str, config: TTSConfig, temperature: float | None = None) -> dict:
    body: dict = {
        "text": text,
        "target_language_code": target_language(config.language),
        "model": _MODEL,
        "speaker": resolve_speaker(config.voice_id),
        "speech_sample_rate": config.sample_rate,
        "pace": clamp_pace(config.speed),
        "temperature": clamp_temperature(
            temperature if temperature is not None else config.extra.get("temperature", DEFAULT_TEMPERATURE)
        ),
    }
    if config.extra.get("dict_id"):
        body["dict_id"] = config.extra["dict_id"]
    return body


def build_headers(api_key: str) -> dict:
    return {"api-subscription-key": api_key, "Content-Type": "application/json"}


# ── WebSocket (consumed by the sarvamai SDK via ws_client.py) ──────────────
def build_ws_config(config: TTSConfig) -> dict:
    return {
        "type": "config",
        "data": {
            "target_language_code": target_language(config.language),
            "speaker": resolve_speaker(config.voice_id),
            "pace": clamp_pace(config.speed),
            "min_buffer_size": 50,
            "max_chunk_length": 200,
            "output_audio_codec": "linear16",
        },
    }
