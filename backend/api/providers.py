"""
Provider capability metadata for the frontend.

GET /api/providers returns the TTS/STT providers the backend supports, plus
per-provider UI hints (voice_id_optional, supports_tone, etc.). The frontend
fetches this and falls back to hardcoded constants if the request fails.

The provider *names* are sourced from the installed packages' registries, so a
newly registered provider shows up here automatically. Capability flags are
declared in the small tables below.

No secrets or env voice IDs are ever exposed here.
"""
from fastapi import APIRouter

from module.stt_core.registry import list_providers as list_stt_providers
from module.tts_core.registry import list_providers as list_tts_providers
from module.noise_cancellation_core.registry import list_providers as list_nc_providers

router = APIRouter(prefix="/api/providers", tags=["providers"])

_LABELS = {
    "cartesia": "Cartesia",
    "sarvam": "Sarvam (v2)",
    "sarvam-v3": "Sarvam Bulbul v3",
    "deepgram": "Deepgram",
    "quail": "Quail",
}

# Per-provider UI capability hints (safe, non-secret).
_TTS_CAPS = {
    "cartesia": {
        "supports_streaming": True,
        "supports_voice_id": True,
        "supports_tone": True,
        "supports_speed": True,
        "supports_pitch": False,
        "default_sample_rate": 24000,
        "voice_id_optional": True,
        "voice_id_fallback": "env_by_language",
    },
    "sarvam": {
        "supports_streaming": False,
        "supports_voice_id": True,
        "supports_tone": False,
        "supports_speed": True,
        "supports_pitch": True,
        "default_sample_rate": 8000,
        "voice_id_optional": True,
        "voice_id_fallback": "none",
    },
    "sarvam-v3": {
        "supports_streaming": True,
        "supports_voice_id": True,
        "supports_tone": False,
        "supports_speed": True,
        "supports_pitch": False,
        "default_sample_rate": 24000,
        "voice_id_optional": True,
        "voice_id_fallback": "default_shubh",
    },
}

_STT_CAPS = {
    "sarvam": {"supports_model": True, "supports_auto_language": True},
    "deepgram": {"supports_model": True, "supports_auto_language": True},
}


_NC_CAPS = {
    "quail": {"supports_model": False, "real_time": True},
}


def _label(name: str) -> str:
    return _LABELS.get(name, name.capitalize())


def _tts_entry(name: str) -> dict:
    caps = _TTS_CAPS.get(name, {})
    return {"value": name, "label": _label(name), **caps}


def _stt_entry(name: str) -> dict:
    caps = _STT_CAPS.get(name, {})
    return {"value": name, "label": _label(name), **caps}


def _nc_entry(name: str) -> dict:
    caps = _NC_CAPS.get(name, {})
    return {"value": name, "label": _label(name), **caps}


@router.get("")
def get_providers():
    return {
        "tts": [_tts_entry(n) for n in list_tts_providers()],
        "stt": [_stt_entry(n) for n in list_stt_providers()],
        "noise_cancellation": [_nc_entry(n) for n in list_nc_providers()],
    }
