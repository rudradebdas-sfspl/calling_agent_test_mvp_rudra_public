"""Sarvam Bulbul v3-specific TTS exceptions."""
from __future__ import annotations

from module.tts_core.errors import SynthesisError


class SarvamV3TTSError(SynthesisError):
    """Base class for Sarvam Bulbul v3 TTS failures."""
