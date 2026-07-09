"""
Cartesia mapping logic — tone/style mapping + voice ID resolution.

Voice ID resolution priority:
    1. config.voice_id            (from frontend / database, if provided)
    2. config.extra["voice_id"]   (provider advanced config, if provided)
    3. language-specific voice ID from the environment
    4. otherwise -> raise CartesiaVoiceConfigError

Required env vars:
    Hindi    -> CARTESIA_HINDI_VOICE_ID    or CARTESIA_VOICE_ID_HI
    Bengali  -> CARTESIA_BENGALI_VOICE_ID  or CARTESIA_VOICE_ID_BN
    English  -> CARTESIA_ENGLISH_VOICE_ID  or CARTESIA_VOICE_ID_EN
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from module.tts_core.base import TTSConfig
from module.tts_core.providers.cartesia.errors import CartesiaVoiceConfigError

# ---------------------------------------------------------------------------
# Tone / style mapping
# ---------------------------------------------------------------------------

_TONE_TABLE = {
    "neutral":       {"speed": "normal", "emotion": []},
    "professional":  {"speed": "normal", "emotion": ["positivity:low"]},
    "friendly":      {"speed": "normal", "emotion": ["positivity:high"]},
    "calm":          {"speed": "slow",   "emotion": ["positivity:low"]},
    "energetic":     {"speed": "fast",   "emotion": ["positivity:high", "surprise:high"]},
    "empathetic":    {"speed": "slow",   "emotion": ["sadness:low", "positivity:low"]},
    "serious":       {"speed": "normal", "emotion": ["positivity:lowest"]},
    "support-agent": {"speed": "normal", "emotion": ["positivity:low"]},
    "sales-agent":   {"speed": "fast",   "emotion": ["positivity:high"]},
    "custom":        {"speed": "normal", "emotion": []},
}

_SPEED_ORDER = ["slowest", "slow", "normal", "fast", "fastest"]


def _numeric_to_speed_enum(speed: float, base: str) -> str:
    base_idx = _SPEED_ORDER.index(base) if base in _SPEED_ORDER else 2
    if speed <= 0.6:
        idx = 0
    elif speed <= 0.85:
        idx = 1
    elif speed < 1.15:
        idx = base_idx
    elif speed < 1.5:
        idx = 3
    else:
        idx = 4
    return _SPEED_ORDER[idx]


@dataclass
class CartesiaVoiceControls:
    speed: str
    emotion: list[str]
    style_instruction: str | None
    pitch: float
    volume: float


def map_tone_to_cartesia(config: TTSConfig) -> CartesiaVoiceControls:
    table = _TONE_TABLE.get(config.tone, _TONE_TABLE["neutral"])
    speed_enum = _numeric_to_speed_enum(config.speed, table["speed"])

    emotion = list(table["emotion"])
    if config.emotion:
        emotion = [config.emotion] if ":" in config.emotion else [f"{config.emotion}:high"]

    style_instruction = config.style_prompt.strip() if config.style_prompt else None

    return CartesiaVoiceControls(
        speed=speed_enum,
        emotion=emotion,
        style_instruction=style_instruction,
        pitch=config.pitch,
        volume=config.volume,
    )


# ---------------------------------------------------------------------------
# Voice ID resolution (env-based fallback)
# ---------------------------------------------------------------------------

_LANG_ENV_VARS: dict[str, list[str]] = {
    "hi": ["CARTESIA_HINDI_VOICE_ID", "CARTESIA_VOICE_ID_HI"],
    "bn": ["CARTESIA_BENGALI_VOICE_ID", "CARTESIA_VOICE_ID_BN"],
    "en": ["CARTESIA_ENGLISH_VOICE_ID", "CARTESIA_VOICE_ID_EN"],
}

_LANG_DISPLAY = {"hi": "Hindi", "bn": "Bengali", "en": "English"}

_LANG_ALIASES: dict[str, str] = {
    "hi": "hi", "hi-in": "hi", "hindi": "hi",
    "bn": "bn", "bn-in": "bn", "bengali": "bn", "bangla": "bn",
    "en": "en", "en-in": "en", "en-us": "en", "en-gb": "en", "english": "en",
}


def normalize_language(language: Optional[str]) -> Optional[str]:
    """Map a free-form language string to 'hi' | 'bn' | 'en', or None if unknown."""
    if not language:
        return None
    key = language.strip().lower()
    if key in _LANG_ALIASES:
        return _LANG_ALIASES[key]
    prefix = key.split("-", 1)[0]
    return _LANG_ALIASES.get(prefix)


def _env_voice_id(lang_key: str) -> Optional[str]:
    for var in _LANG_ENV_VARS.get(lang_key, []):
        val = os.getenv(var)
        if val and val.strip():
            return val.strip()
    return None


def resolve_voice_id(config: TTSConfig) -> str:
    """Resolve the final Cartesia voice ID. Raises CartesiaVoiceConfigError if none found."""
    if config.voice_id and config.voice_id.strip():
        return config.voice_id.strip()

    extra_voice = config.extra.get("voice_id") if isinstance(config.extra, dict) else None
    if extra_voice and str(extra_voice).strip():
        return str(extra_voice).strip()

    lang_key = normalize_language(config.language)
    if lang_key is not None:
        env_voice = _env_voice_id(lang_key)
        if env_voice:
            return env_voice
        a, b = _LANG_ENV_VARS[lang_key]
        raise CartesiaVoiceConfigError(
            f"Cartesia voice ID is missing for {_LANG_DISPLAY[lang_key]}. "
            f"Please set {a} or {b} in env."
        )

    raise CartesiaVoiceConfigError(
        f"Cartesia voice ID was not provided and language "
        f"'{config.language}' has no env voice mapping. Pass a voice_id or set "
        f"one of CARTESIA_HINDI_VOICE_ID / CARTESIA_BENGALI_VOICE_ID / "
        f"CARTESIA_ENGLISH_VOICE_ID (or the *_VOICE_ID_HI/BN/EN variants)."
    )
