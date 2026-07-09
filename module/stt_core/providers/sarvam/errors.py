"""Sarvam-specific STT exceptions (subclass package-level errors)."""
from __future__ import annotations

from module.stt_core.errors import TranscriptionError


class SarvamSTTError(TranscriptionError):
    """Base class for Sarvam STT failures."""
