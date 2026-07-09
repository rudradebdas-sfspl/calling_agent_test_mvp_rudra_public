"""
Cache service — the bridge between the reusable `module/redis_core` and this app.

Just like services/stt/factory.py and services/tts/factory.py, this reads
connection settings from `backend.config.settings` and builds ONE shared cache
instance for the whole process.

Usage anywhere in the backend or worker:

    from backend.services.cache import get_cache

    cache = get_cache()
    await cache.set_json("kb:<hash>", chunks, ttl=300)
    chunks = await cache.get_json("kb:<hash>")
"""
from __future__ import annotations

import logging

from backend.config import settings
from module.redis_core.base import BaseCache, CacheConfig
from module.redis_core.registry import create_provider

log = logging.getLogger("cache")

_cache: BaseCache | None = None


def get_cache() -> BaseCache:
    """Return the process-wide cache singleton (built on first call)."""
    global _cache
    if _cache is None:
        backend = getattr(settings, "CACHE_BACKEND", "redis")
        config = CacheConfig(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            namespace=settings.REDIS_NAMESPACE,
        )
        _cache = create_provider(backend, config=config)
        log.info(
            "Cache backend=%s host=%s:%s db=%s ns=%r",
            backend, config.host, config.port, config.db, config.namespace,
        )
    return _cache


async def close_cache() -> None:
    """Close the cache on app shutdown (call from FastAPI shutdown / worker exit)."""
    global _cache
    if _cache is not None:
        await _cache.close()
        _cache = None