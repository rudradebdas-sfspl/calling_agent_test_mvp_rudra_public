"""Exceptions raised by tts_core."""


class TTSError(Exception):
    """Base class for all tts_core errors."""


class ProviderNotFound(TTSError):
    """Raised when create_provider() is given an unknown provider name."""


class MissingCredentials(TTSError):
    """Raised when a provider is built without the credentials it needs."""


class SynthesisError(TTSError):
    """Raised when the upstream TTS API call fails."""
