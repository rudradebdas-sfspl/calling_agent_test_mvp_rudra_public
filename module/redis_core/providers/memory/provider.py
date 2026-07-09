"""
In-memory cache backend (async, TTL-aware).

A zero-dependency drop-in that implements the same BaseCache contract as the
Redis backend. Useful for local dev, unit tests, or single-process deployments
where running a Redis server is overkill.

NOTE: state lives in this process only — it is NOT shared across workers and is
lost on restart. For multi-worker / production use the redis backend.
"""
from __future__ import annotations

import time
from typing import Optional

from module.redis_core.base import BaseCache, CacheConfig
from module.redis_core.registry import register_provider


@register_provider("memory")
class MemoryCache(BaseCache):
    def __init__(self, config: Optional[CacheConfig] = None):
        super().__init__(config)
        # key -> (value, expires_at_epoch | None)
        self._store: dict[str, tuple[str, Optional[float]]] = {}

    def _alive(self, key: str) -> Optional[tuple[str, Optional[float]]]:
        item = self._store.get(key)
        if item is None:
            return None
        _, expires_at = item
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return item

    async def get(self, key: str) -> Optional[str]:
        item = self._alive(self._key(key))
        return item[0] if item else None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        ttl = self._ttl(ttl)
        expires_at = time.monotonic() + ttl if ttl else None
        self._store[self._key(key)] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(self._key(key), None)

    async def exists(self, key: str) -> bool:
        return self._alive(self._key(key)) is not None

    async def incr(self, key: str, amount: int = 1) -> int:
        k = self._key(key)
        item = self._alive(k)
        current = int(item[0]) if item else 0
        new_val = current + amount
        expires_at = item[1] if item else None
        self._store[k] = (str(new_val), expires_at)
        return new_val

    async def expire(self, key: str, ttl: int) -> None:
        k = self._key(key)
        item = self._alive(k)
        if item:
            self._store[k] = (item[0], time.monotonic() + ttl)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._store.clear()