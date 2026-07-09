import asyncio
import os

import pytest

from module.redis_core.base import CacheConfig
from module.redis_core.providers.redis.provider import RedisCache


@pytest.mark.asyncio
async def test_real_redis_cache_roundtrip():
    cache = RedisCache(
        CacheConfig(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "1")),
            namespace="ci",
        )
    )
    try:
        assert await cache.ping() is True
        await cache.set_json("session:test", {"messages": ["hello"]}, ttl=30)
        assert await cache.get_json("session:test") == {"messages": ["hello"]}
        assert await cache.incr("rate:test") == 1
        await cache.expire("rate:test", 1)
        assert await cache.exists("rate:test") is True
        await asyncio.sleep(1.1)
        assert await cache.exists("rate:test") is False
    finally:
        await cache.delete("session:test")
        await cache.close()