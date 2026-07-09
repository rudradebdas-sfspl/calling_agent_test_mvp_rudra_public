"""Deepgram-specific STT exceptions (subclass package-level errors)."""
from __future__ import annotations

from module.stt_core.errors import TranscriptionError


class DeepgramSTTError(TranscriptionError):
    """Base class for Deepgram STT failures."""
