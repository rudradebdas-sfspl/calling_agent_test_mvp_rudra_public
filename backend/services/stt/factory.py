"""
STT adapter.

This is the ONLY place that knows about both the app (agent ORM rows, .env) and
the backend.stt_core module. It maps an agent's stored STT settings + the
server's API keys onto stt_core, then returns a ready provider.
"""
from module.stt_core.base import STTConfig, BaseSTTProvider
from module.stt_core.registry import create_provider

from backend.config import settings


def _resolve(provider: str, agent) -> tuple[STTConfig, dict]:
    """Build (config, credentials) for the chosen provider, applying .env defaults."""
    if provider == "sarvam":
        config = STTConfig(
            language_code=agent.stt_language_code or settings.SARVAM_STT_DEFAULT_LANGUAGE_CODE,
            auto_language_detection=agent.stt_auto_language_detection,
        )
        return config, {"api_key": settings.SARVAM_API_KEY}

    if provider == "deepgram":
        config = STTConfig(
            language_code=agent.stt_language_code or settings.DEEPGRAM_STT_DEFAULT_LANGUAGE,
            auto_language_detection=agent.stt_auto_language_detection,
        )
        return config, {"api_key": settings.DEEPGRAM_API_KEY}

    raise ValueError(f"Unknown stt_provider: {provider}")


class STTProviderFactory:
    @staticmethod
    def create(agent) -> BaseSTTProvider:
        provider = agent.stt_provider
        config, credentials = _resolve(provider, agent)
        return create_provider(provider, config=config, **credentials)
