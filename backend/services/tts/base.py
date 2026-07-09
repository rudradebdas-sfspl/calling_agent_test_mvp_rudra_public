"""
Backward-compatible shim.

The TTS contracts now live in the standalone `tts_core` package. This module
re-exports them so any existing `from backend.services.tts.base import ...`
keeps working.
"""
from module.tts_core.base import BaseTTSProvider, OutputFormat, TTSConfig  # noqa: F401

__all__ = ["BaseTTSProvider", "OutputFormat", "TTSConfig"]
