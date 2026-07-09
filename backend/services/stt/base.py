"""
Backward-compatible shim.

The STT contracts now live in the standalone `stt_core` package. This module
re-exports them so any existing `from backend.services.stt.base import ...`
keeps working.
"""
from module.stt_core.base import BaseSTTProvider, STTConfig, STTResult  # noqa: F401

__all__ = ["BaseSTTProvider", "STTConfig", "STTResult"]
