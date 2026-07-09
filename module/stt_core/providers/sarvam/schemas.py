"""
Sarvam STT request builders (plain Python, not DB schemas).

Sarvam accepts a WAV file upload plus a language code. The model is pinned
below. When auto_language_detection is on, language "unknown" is sent.
"""
from __future__ import annotations

import io

from module.stt_core.audio import pcm_to_wav
from module.stt_core.base import STTConfig

DEFAULT_LANGUAGE = "bn-IN"

# --- Sarvam STT model (pinned) ---------------------------------------------
# saaras:v3 with mode="transcribe" gives the best proper-noun / entity
# preservation and telephony (8kHz) handling, which keeps IT system names
# (ESAF, NexID, Fedmi, Wi-Fi, TMS, M-Bank) from being mis-transcribed.
# To fall back to the legacy model, set STT_MODEL = "saarika:v2.5" and
# STT_MODE = None (mode is only used by saaras:v3).
STT_MODEL = "saaras:v3"
STT_MODE = "transcribe"


def resolve_language(config: STTConfig) -> str:
    if config.auto_language_detection:
        return "unknown"
    return config.language_code or DEFAULT_LANGUAGE


def build_multipart(audio: bytes, sample_rate: int, config: STTConfig):
    """Return (files, data) for httpx multipart upload."""
    wav_audio = pcm_to_wav(audio, sample_rate)
    files = {"file": ("audio.wav", io.BytesIO(wav_audio), "audio/wav")}
    data = {
        "language_code": resolve_language(config),
        "model": STT_MODEL,
    }
    if STT_MODE:
        data["mode"] = STT_MODE  # only meaningful for saaras:v3
    return files, data


def build_headers(api_key: str) -> dict:
    return {"api-subscription-key": api_key}


def parse_response(payload: dict, requested_language: str):
    """Return (text, language) from a Sarvam STT JSON response."""
    text = (payload.get("transcript") or "").strip()
    language = payload.get("language_code") or requested_language
    return text, language