"""Exceptions raised by stt_core."""


class STTError(Exception):
    """Base class for all stt_core errors."""


class ProviderNotFound(STTError):
    """Raised when create_provider() is given an unknown provider name."""


class MissingCredentials(STTError):
    """Raised when a provider is built without the credentials it needs."""


class TranscriptionError(STTError):
    """Raised when the upstream STT API call fails."""
