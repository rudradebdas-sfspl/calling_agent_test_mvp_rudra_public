"""
Provider registry — the heart of the pluggable design.

A provider registers itself by name with @register_provider("name"). Callers then
build one by name with create_provider("name", ...) without importing the class.
"""
from __future__ import annotations

import os
from typing import Optional, Type

from module.stt_core.base import BaseSTTProvider, STTConfig
from module.stt_core.errors import MissingCredentials, ProviderNotFound

_REGISTRY: dict[str, Type[BaseSTTProvider]] = {}


def register_provider(name: str):
    """Class decorator that registers a provider under `name` (case-insensitive)."""
    def _decorator(cls: Type[BaseSTTProvider]) -> Type[BaseSTTProvider]:
        if not issubclass(cls, BaseSTTProvider):
            raise TypeError(f"{cls!r} must subclass BaseSTTProvider")
        _REGISTRY[name.lower()] = cls
        return cls
    return _decorator


def list_providers() -> list[str]:
    """Names of all registered providers."""
    _load_providers()
    return sorted(_REGISTRY)


def get_provider_class(name: str) -> Type[BaseSTTProvider]:
    _load_providers()
    try:
        return _REGISTRY[name.lower()]
    except KeyError:
        raise ProviderNotFound(
            f"Unknown STT provider '{name}'. Registered: {list_providers()}"
        )


def create_provider(
    name: str,
    *,
    config: Optional[STTConfig] = None,
    **credentials,
) -> BaseSTTProvider:
    """
    Build a provider by name with explicit credentials.

    Example:
        stt = create_provider("sarvam", api_key="...",
                             config=STTConfig(language_code="bn-IN"))
    """
    cls = get_provider_class(name)
    creds = {k: v for k, v in credentials.items() if v is not None}
    return cls(config=config, **creds)


def from_env(
    name: str,
    *,
    config: Optional[STTConfig] = None,
    prefix: Optional[str] = None,
) -> BaseSTTProvider:
    """Build a provider reading credentials from environment variables."""
    env_prefix = prefix if prefix is not None else f"STT_{name.upper()}_"
    api_key = os.getenv(env_prefix + "API_KEY")
    base_url = os.getenv(env_prefix + "BASE_URL")
    if not api_key:
        raise MissingCredentials(f"{env_prefix}API_KEY is not set in the environment")
    return create_provider(name, config=config, api_key=api_key, base_url=base_url)


def _load_providers():
    """Lazily import providers so they register themselves."""
    if not _REGISTRY:
        import module.stt_core.providers.deepgram.provider  # noqa: F401
        import module.stt_core.providers.sarvam.provider    # noqa: F401
