"""
Deepgram STT request builders (plain Python, not DB schemas).

Model is hardcoded to "nova-3".
"""
from __future__ import annotations

from module.stt_core.base import STTConfig

_MODEL = "nova-3"
DEFAULT_LANGUAGE = "en-IN"


def build_params(config: STTConfig, sample_rate: int) -> dict:
    params = {
        "model": _MODEL,
        "encoding": "linear16",
        "sample_rate": str(sample_rate),
        "smart_format": "true",
    }
    if config.auto_language_detection:
        params["detect_language"] = "true"
    else:
        params["language"] = config.language_code or DEFAULT_LANGUAGE
    return params


def build_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/raw",
    }


def parse_response(payload: dict, config: STTConfig, params: dict):
    """Return (text, language) from a Deepgram listen response."""
    channel = payload["results"]["channels"][0]
    alt = channel["alternatives"][0]
    detected = (
        channel.get("detected_language")
        if config.auto_language_detection
        else params.get("language")
    )
    return (alt.get("transcript") or "").strip(), detected
