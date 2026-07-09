"""Sarvam TTS request payload builders (plain Python dicts)."""
from __future__ import annotations

from module.tts_core.base import TTSConfig
from module.tts_core.providers.sarvam.mapper import target_language

_MODEL = "bulbul:v2"


def build_tts_body(text: str, config: TTSConfig) -> dict:
    body = {
        "inputs": [text],
        "target_language_code": target_language(config.language),
        "speech_sample_rate": config.sample_rate,
        "pace": config.speed,
        "pitch": config.pitch,
        "loudness": config.volume,
        "enable_preprocessing": True,
        "model": _MODEL,
    }
    if config.voice_id:
        body["speaker"] = config.voice_id
    return body


def build_headers(api_key: str) -> dict:
    return {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }
