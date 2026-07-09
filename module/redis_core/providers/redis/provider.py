"""
Redis cache backend (async).

Implements the BaseCache contract on top of redis-py's async client. The client
is created lazily on first use so that constructing the provider never blocks or
fails just because Redis is momentarily down.
"""
from __future__ import annotations

from typing import Optional

from module.redis_core.base import BaseCache, CacheConfig
from module.redis_core.providers.redis.client import build_client
from module.redis_core.providers.redis.errors import RedisCacheError
from module.redis_core.registry import register_provider


@register_provider("redis")
class RedisCache(BaseCache):
    def __init__(self, config: Optional[CacheConfig] = None):
        super().__init__(config)
        self._client = None  # built lazily

    @property
    def client(self):
        if self._client is None:
            self._client = build_client(self.config)
        return self._client

    async def get(self, key: str) -> Optional[str]:
        try:
            return await self.client.get(self._key(key))
        except Exception as exc:
            raise RedisCacheError(f"GET failed for {key!r}: {exc}") from exc

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        ttl = self._ttl(ttl)
        try:
            # ex=None means no expiry; ex must be a positive int otherwise.
            await self.client.set(self._key(key), value, ex=ttl if ttl else None)
        except Exception as exc:
            raise RedisCacheError(f"SET failed for {key!r}: {exc}") from exc

    async def delete(self, key: str) -> None:
        try:
            await self.client.delete(self._key(key))
        except Exception as exc:
            raise RedisCacheError(f"DELETE failed for {key!r}: {exc}") from exc

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.client.exists(self._key(key)))
        except Exception as exc:
            raise RedisCacheError(f"EXISTS failed for {key!r}: {exc}") from exc

    async def incr(self, key: str, amount: int = 1) -> int:
        try:
            return int(await self.client.incrby(self._key(key), amount))
        except Exception as exc:
            raise RedisCacheError(f"INCR failed for {key!r}: {exc}") from exc

    async def expire(self, key: str, ttl: int) -> None:
        try:
            await self.client.expire(self._key(key), ttl)
        except Exception as exc:
            raise RedisCacheError(f"EXPIRE failed for {key!r}: {exc}") from exc

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception:
            return False

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except AttributeError:  # older redis-py used .close()
                await self._client.close()
            self._client = None