"""
Backend registry — the heart of the pluggable design (same as stt_core / tts_core).

A backend registers itself by name with @register_provider("name"). Callers then
build one by name with create_provider("name", ...) without importing the class.
"""
from __future__ import annotations

import os
from typing import Optional, Type

from module.redis_core.base import BaseCache, CacheConfig
from module.redis_core.errors import BackendNotFound

_REGISTRY: dict[str, Type[BaseCache]] = {}


def register_provider(name: str):
    """Class decorator that registers a backend under `name` (case-insensitive)."""
    def _decorator(cls: Type[BaseCache]) -> Type[BaseCache]:
        if not issubclass(cls, BaseCache):
            raise TypeError(f"{cls!r} must subclass BaseCache")
        _REGISTRY[name.lower()] = cls
        return cls
    return _decorator


def list_providers() -> list[str]:
    """Names of all registered backends."""
    _load_providers()
    return sorted(_REGISTRY)


def get_provider_class(name: str) -> Type[BaseCache]:
    _load_providers()
    try:
        return _REGISTRY[name.lower()]
    except KeyError:
        raise BackendNotFound(
            f"Unknown cache backend '{name}'. Registered: {list_providers()}"
        )


def create_provider(
    name: str = "redis",
    *,
    config: Optional[CacheConfig] = None,
) -> BaseCache:
    """
    Build a cache backend by name.

    Example:
        cache = create_provider("redis", config=CacheConfig(host="localhost", port=6379))
        cache = create_provider("memory")   # no Redis needed (tests / fallback)
    """
    cls = get_provider_class(name)
    return cls(config=config)


def from_env(
    name: str = "redis",
    *,
    prefix: str = "REDIS_",
    namespace: str = "",
    default_ttl: Optional[int] = None,
) -> BaseCache:
    """
    Build a backend reading connection settings from environment variables.

    Reads (with the given prefix, default "REDIS_"):
        {prefix}URL        e.g. redis://:pass@host:6379/0   (wins if set)
        {prefix}HOST       default "localhost"
        {prefix}PORT       default 6379
        {prefix}DB         default 0
        {prefix}PASSWORD   optional
    """
    config = CacheConfig(
        url=os.getenv(prefix + "URL") or None,
        host=os.getenv(prefix + "HOST", "localhost"),
        port=int(os.getenv(prefix + "PORT", "6379") or 6379),
        db=int(os.getenv(prefix + "DB", "0") or 0),
        password=os.getenv(prefix + "PASSWORD") or None,
        namespace=namespace,
        default_ttl=default_ttl,
    )
    return create_provider(name, config=config)


def _load_providers():
    """Lazily import backends so they register themselves."""
    if not _REGISTRY:
        import module.redis_core.providers.redis.provider   # noqa: F401
        import module.redis_core.providers.memory.provider  # noqa: F401