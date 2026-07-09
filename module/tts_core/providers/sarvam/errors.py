"""Sarvam-specific TTS exceptions."""
from __future__ import annotations

from module.tts_core.errors import SynthesisError


class SarvamTTSError(SynthesisError):
    """Base class for Sarvam TTS failures."""
