"""
Provider registry — the heart of the pluggable design.

A provider registers itself by name with @register_provider("name"). Callers then
build one by name with create_provider("name", ...) without importing the class.
"""
from __future__ import annotations

import os
from typing import Optional, Type

from module.tts_core.base import BaseTTSProvider, TTSConfig
from module.tts_core.errors import MissingCredentials, ProviderNotFound

_REGISTRY: dict[str, Type[BaseTTSProvider]] = {}


def register_provider(name: str):
    """Class decorator that registers a provider under `name` (case-insensitive)."""
    def _decorator(cls: Type[BaseTTSProvider]) -> Type[BaseTTSProvider]:
        if not issubclass(cls, BaseTTSProvider):
            raise TypeError(f"{cls!r} must subclass BaseTTSProvider")
        _REGISTRY[name.lower()] = cls
        return cls
    return _decorator


def list_providers() -> list[str]:
    """Names of all registered providers."""
    _load_providers()
    return sorted(_REGISTRY)


def get_provider_class(name: str) -> Type[BaseTTSProvider]:
    _load_providers()
    try:
        return _REGISTRY[name.lower()]
    except KeyError:
        raise ProviderNotFound(
            f"Unknown TTS provider '{name}'. Registered: {list_providers()}"
        )


def create_provider(
    name: str,
    *,
    config: Optional[TTSConfig] = None,
    **credentials,
) -> BaseTTSProvider:
    """
    Build a provider by name with explicit credentials.

    Example:
        tts = create_provider("cartesia", api_key="sk-...",
                              config=TTSConfig(voice_id="abc", tone="friendly"))
    """
    cls = get_provider_class(name)
    creds = {k: v for k, v in credentials.items() if v is not None}
    return cls(config=config, **creds)


def from_env(
    name: str,
    *,
    config: Optional[TTSConfig] = None,
    prefix: Optional[str] = None,
) -> BaseTTSProvider:
    """Build a provider reading credentials from environment variables."""
    if prefix is None:
        prefix = f"{name.upper()}_"
    api_key = os.getenv(prefix + "API_KEY")
    base_url = os.getenv(prefix + "BASE_URL")
    if not api_key:
        raise MissingCredentials(f"{prefix}API_KEY is not set in the environment")
    return create_provider(name, config=config, api_key=api_key, base_url=base_url)


def _load_providers():
    """Lazily import providers so they register themselves."""
    if not _REGISTRY:
        import module.tts_core.providers.cartesia.provider   # noqa: F401
        import module.tts_core.providers.sarvam.provider      # noqa: F401
        import module.tts_core.providers.sarvam_v3.provider   # noqa: F401
