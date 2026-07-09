"""Cartesia-specific exceptions."""
from __future__ import annotations

from module.tts_core.errors import MissingCredentials, SynthesisError


class CartesiaError(SynthesisError):
    """Base class for Cartesia-specific synthesis failures."""


class CartesiaVoiceConfigError(MissingCredentials):
    """Raised when no Cartesia voice ID can be resolved."""
