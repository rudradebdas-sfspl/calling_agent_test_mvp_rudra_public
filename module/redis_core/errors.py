"""Exceptions raised by redis_core."""


class CacheError(Exception):
    """Base class for all redis_core errors."""


class BackendNotFound(CacheError):
    """Raised when create_provider() is given an unknown backend name."""


class MissingDependency(CacheError):
    """Raised when a backend needs a package that isn't installed (e.g. `redis`)."""


class ConnectionFailed(CacheError):
    """Raised when the cache backend cannot be reached."""