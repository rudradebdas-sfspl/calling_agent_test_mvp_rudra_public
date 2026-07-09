"""Cartesia request payload builders."""
from __future__ import annotations

from typing import Optional

from module.tts_core.providers.cartesia.mapper import CartesiaVoiceControls

CARTESIA_VERSION = "2024-06-10"


def build_transcript(text: str, controls: CartesiaVoiceControls) -> str:
    """Prepend an optional style instruction to the spoken transcript."""
    if controls.style_instruction:
        return f"[{controls.style_instruction}] {text}"
    return text


def build_tts_body(
    *,
    model: str,
    transcript: str,
    voice_id: str,
    language: str,
    sample_rate: int,
    controls: CartesiaVoiceControls,
) -> dict:
    """Build the JSON body for Cartesia's /tts/bytes endpoint."""
    return {
        "model_id": model,
        "transcript": transcript,
        "voice": {"mode": "id", "id": voice_id},
        "language": language,
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": sample_rate,
        },
        "__experimental_controls": {
            "speed": controls.speed,
            "emotion": controls.emotion,
        },
    }


def build_headers(api_key: str, *, version: Optional[str] = None) -> dict:
    return {
        "X-API-Key": api_key,
        "Cartesia-Version": version or CARTESIA_VERSION,
        "Content-Type": "application/json",
    }
