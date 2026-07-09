"""
TTS adapter (thin).

This is the ONLY place that knows about both the app (agent ORM rows, .env) and
the backend.tts_core module. It maps an agent's stored TTS settings + the
server's API keys onto tts_core, then returns a ready provider.

Model names are hardcoded inside tts_core providers (sonic-3 for Cartesia,
bulbul:v2 for Sarvam). Only api_key is needed here.
"""
from module.tts_core.base import TTSConfig, BaseTTSProvider
from module.tts_core.registry import create_provider

from backend.config import settings


def _credentials_for(provider: str) -> dict:
    """Per-provider credentials pulled from .env. Model is hardcoded in the provider."""
    if provider == "cartesia":
        return {"api_key": settings.CARTESIA_API_KEY}
    if provider == "sarvam":
        return {"api_key": settings.SARVAM_API_KEY}
    if provider == "sarvam-v3":
        return {
            "api_key": settings.SARVAM_API_KEY,
            "temperature": settings.SARVAM_V3_TEMPERATURE,
            "use_websocket": settings.SARVAM_V3_USE_WEBSOCKET,
        }
    raise ValueError(f"Unknown tts_provider: {provider}")


def _saved_voice_id(provider: str, agent) -> str | None:
    if provider == "cartesia":
        return agent.cartesia_voice_id or None
    if provider == "sarvam":
        return agent.cartesia_voice_id or settings.SARVAM_TTS_DEFAULT_SPEAKER or None
    if provider == "sarvam-v3":
        return agent.cartesia_voice_id or settings.SARVAM_V3_DEFAULT_SPEAKER or None
    return None


def _sample_rate_for(provider: str) -> int:
    if provider == "sarvam":
        return settings.TTS_SAMPLE_RATE
    # sarvam-v3 and cartesia both default to 24kHz
    return 24000


class TTSProviderFactory:
    @staticmethod
    def create(agent) -> BaseTTSProvider:
        provider = agent.tts_provider
        config = TTSConfig(
            voice_id=_saved_voice_id(provider, agent),
            language=agent.tts_language,
            speed=agent.tts_speed,
            pitch=agent.tts_pitch,
            volume=agent.tts_volume,
            emotion=agent.tts_emotion,
            tone=agent.tts_tone,
            style_prompt=agent.tts_style_prompt,
            sample_rate=_sample_rate_for(provider),
        )
        return create_provider(provider, config=config, **_credentials_for(provider))
