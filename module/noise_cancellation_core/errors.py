"""Exceptions for noise_cancellation_core."""


class NoiseCancellationError(Exception):
    """Base class for all noise_cancellation_core errors."""


class ProviderNotFound(NoiseCancellationError):
    """Raised when create_provider() is given an unknown provider name."""


class MissingCredentials(NoiseCancellationError):
    """Raised when a provider is built without the credentials it needs."""
