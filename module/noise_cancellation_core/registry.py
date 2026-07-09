"""
Provider registry — the heart of the pluggable design.

A provider registers itself by name with @register_provider("name"). Callers then
build one by name with create_provider("name", ...) without importing the class.

Add a new provider by creating module/noise_cancellation_core/providers/<name>/
and registering it here in _load_providers(). No other file changes needed.
"""
from __future__ import annotations

import os
from typing import Optional, Type

from module.noise_cancellation_core.base import BaseNoiseCanceller, NoiseCancellationConfig
from module.noise_cancellation_core.errors import ProviderNotFound

_REGISTRY: dict[str, Type[BaseNoiseCanceller]] = {}


def register_provider(name: str):
    """Class decorator that registers a provider under `name` (case-insensitive)."""
    def _decorator(cls: Type[BaseNoiseCanceller]) -> Type[BaseNoiseCanceller]:
        if not issubclass(cls, BaseNoiseCanceller):
            raise TypeError(f"{cls!r} must subclass BaseNoiseCanceller")
        _REGISTRY[name.lower()] = cls
        return cls
    return _decorator


def list_providers() -> list[str]:
    """Names of all registered providers."""
    _load_providers()
    return sorted(_REGISTRY)


def get_provider_class(name: str) -> Type[BaseNoiseCanceller]:
    _load_providers()
    try:
        return _REGISTRY[name.lower()]
    except KeyError:
        raise ProviderNotFound(
            f"Unknown noise-cancellation provider '{name}'. Registered: {list_providers()}"
        )


def create_provider(
    name: str,
    *,
    config: Optional[NoiseCancellationConfig] = None,
    **credentials,
) -> BaseNoiseCanceller:
    """
    Build a provider by name with explicit credentials.

    Example:
        nc = create_provider("quail", license_key="...",
                           config=NoiseCancellationConfig(enabled=True))
    """
    cls = get_provider_class(name)
    creds = {k: v for k, v in credentials.items() if v is not None}
    return cls(config=config, **creds)


def from_env(
    name: str,
    *,
    config: Optional[NoiseCancellationConfig] = None,
    prefix: Optional[str] = None,
) -> BaseNoiseCanceller:
    """
    Build a provider reading its license from the environment.

    Default env var pattern (prefix = "NC_<NAME>_"):
        NC_<NAME>_LICENSE   (or NC_<NAME>_API_KEY)

    Providers that read their own env (e.g. Quail reads AIC_SDK_LICENSE) work even
    when this returns no key — the license is simply resolved inside the provider.
    """
    env_prefix = prefix if prefix is not None else f"NC_{name.upper()}_"
    license_key = os.getenv(env_prefix + "LICENSE") or os.getenv(env_prefix + "API_KEY")
    return create_provider(name, config=config, license_key=license_key)


def _load_providers():
    """Lazily import providers so they register themselves."""
    if not _REGISTRY:
        import module.noise_cancellation_core.providers.quail.provider  # noqa: F401
        # Add new providers here, e.g.:
        # import module.noise_cancellation_core.providers.deepfilter.provider  # noqa: F401
