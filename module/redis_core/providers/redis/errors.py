"""Redis-backend-specific errors."""
from module.redis_core.errors import CacheError


class RedisCacheError(CacheError):
    """Raised when a Redis command fails."""