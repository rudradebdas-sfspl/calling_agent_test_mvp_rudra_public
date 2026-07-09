"""
Core contracts for redis_core.

A cache backend takes a `CacheConfig` (connection settings) plus its credentials
and provides simple key/value operations with optional TTL. Nothing here depends
on any web framework, database, or this repo — only the standard library (+ the
`redis` package for the redis provider).

Everything is async so it fits cleanly into async apps (FastAPI, the LiveKit
worker, etc.). The memory provider is async too, so callers can swap backends
without changing a single `await`.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CacheConfig:
    """Connection / behaviour settings. Backend-agnostic; each backend uses what it can."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    # Optional single URL form, e.g. "redis://:pass@host:6379/0". If set, it wins.
    url: Optional[str] = None
    # Prefix prepended to every key, so multiple apps can share one Redis safely.
    namespace: str = ""
    # Default TTL (seconds) applied when set() is called without an explicit ttl.
    # None / 0 means "no expiry".
    default_ttl: Optional[int] = None
    # Seconds to wait before giving up on connect / commands.
    socket_timeout: float = 5.0
    # free-form backend-specific overrides
    extra: dict = field(default_factory=dict)


class BaseCache(ABC):
    """
    Base class every cache backend implements.

    Concrete backends receive their settings via `CacheConfig` so the module stays
    usable in any project. All methods are async.
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()

    # ----- key helper -----------------------------------------------------
    def _key(self, key: str) -> str:
        """Apply the namespace prefix (if any)."""
        ns = self.config.namespace
        return f"{ns}:{key}" if ns else key

    def _ttl(self, ttl: Optional[int]) -> Optional[int]:
        """Resolve the TTL to use: explicit arg wins, else config default."""
        if ttl is not None:
            return ttl
        return self.config.default_ttl

    # ----- raw string ops (must implement) --------------------------------
    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Return the stored string, or None if the key is missing/expired."""
        raise NotImplementedError

    @abstractmethod
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Store a string. `ttl` (seconds) overrides config.default_ttl."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a key (no error if it doesn't exist)."""
        raise NotImplementedError

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """True if the key is present (and not expired)."""
        raise NotImplementedError

    @abstractmethod
    async def incr(self, key: str, amount: int = 1) -> int:
        """Atomically increment an integer counter; returns the new value."""
        raise NotImplementedError

    @abstractmethod
    async def expire(self, key: str, ttl: int) -> None:
        """(Re)set the TTL on an existing key."""
        raise NotImplementedError

    @abstractmethod
    async def ping(self) -> bool:
        """Health check — True if the backend is reachable."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release the connection pool / resources."""
        raise NotImplementedError

    # ----- JSON convenience (built on get/set) ----------------------------
    async def get_json(self, key: str) -> Optional[Any]:
        """Get a value previously stored with set_json(). Returns None if missing."""
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """JSON-encode `value` and store it (with optional TTL)."""
        await self.set(key, json.dumps(value, ensure_ascii=False), ttl=ttl)