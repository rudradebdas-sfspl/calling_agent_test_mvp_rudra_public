"""
Thin wrapper that builds an async redis client from a CacheConfig.

We import `redis.asyncio` lazily inside build_client() so that simply importing
the module (e.g. to use the memory backend) does NOT require the `redis` package
to be installed.
"""
from __future__ import annotations

from module.redis_core.base import CacheConfig
from module.redis_core.errors import MissingDependency


def build_client(config: CacheConfig):
    """
    Return a connected `redis.asyncio.Redis` instance with a pooled connection.

    `decode_responses=True` → all values come back as `str`, not `bytes`, which
    keeps the BaseCache contract (str in / str out) clean.
    """
    try:
        import redis.asyncio as redis  # redis-py >= 4.2 ships the async client
    except ImportError as exc:  # pragma: no cover
        raise MissingDependency(
            "The 'redis' package is required for the redis backend. "
            "Install it with:  pip install redis"
        ) from exc

    if config.url:
        return redis.Redis.from_url(
            config.url,
            decode_responses=True,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.socket_timeout,
            **config.extra,
        )

    return redis.Redis(
        host=config.host,
        port=config.port,
        db=config.db,
        password=config.password,
        decode_responses=True,
        socket_timeout=config.socket_timeout,
        socket_connect_timeout=config.socket_timeout,
        **config.extra,
    )