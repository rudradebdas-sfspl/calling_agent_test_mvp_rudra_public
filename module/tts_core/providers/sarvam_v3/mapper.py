"""
Sarvam Bulbul v3 mapping logic.

1. Language code mapping  (short → BCP-47, e.g. "bn" → "bn-IN")
2. Pace clamping          (0.5–2.0, narrower than v2's 0.3–3.0)
3. Temperature clamping   (0.01–1.0)
4. Speaker resolution     (37 speakers, default "shubh")

DEFAULT_SPEAKER here is the single source of truth for this module. The
backend wiring (backend/config.py's SARVAM_V3_DEFAULT_SPEAKER) should be kept
equal to this value — it exists only so an operator can override it via .env
without touching code, not to introduce a second, different default.
"""
from __future__ import annotations

_FALLBACK_LANGUAGE = "en-IN"

_SHORT_TO_FULL = {
    "bn": "bn-IN", "en": "en-IN", "gu": "gu-IN", "hi": "hi-IN",
    "kn": "kn-IN", "ml": "ml-IN", "mr": "mr-IN", "od": "od-IN",
    "pa": "pa-IN", "ta": "ta-IN", "te": "te-IN",
}

V3_SPEAKERS = frozenset({
    "shubh", "aditya", "ritu", "priya", "neha", "rahul", "pooja", "rohan",
    "simran", "kavya", "amit", "dev", "ishita", "shreya", "ratan", "varun",
    "manan", "sumit", "roopa", "kabir", "aayan", "ashutosh", "advait",
    "anand", "tanya", "tarun", "sunny", "mani", "gokul", "vijay", "shruti",
    "suhani", "mohit", "kavitha", "rehan", "soham", "rupali",
    "amelia", "sophia",
})

DEFAULT_SPEAKER = "shubh"
_MIN_PACE, _MAX_PACE = 0.5, 2.0
_MIN_TEMP, _MAX_TEMP = 0.01, 1.0
DEFAULT_TEMPERATURE = 0.6


def target_language(language: str | None) -> str:
    lang = (language or "").strip() or _FALLBACK_LANGUAGE
    if "-" in lang:
        return lang
    return _SHORT_TO_FULL.get(lang.lower(), _FALLBACK_LANGUAGE)


def clamp_pace(pace: float) -> float:
    return max(_MIN_PACE, min(_MAX_PACE, pace))


def clamp_temperature(temperature: float) -> float:
    return max(_MIN_TEMP, min(_MAX_TEMP, temperature))


def resolve_speaker(voice_id: str | None) -> str:
    if voice_id and voice_id.strip():
        name = voice_id.strip().lower()
        if name in V3_SPEAKERS:
            return name
    return DEFAULT_SPEAKER
