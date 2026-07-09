"""
Core contracts for stt_core.

An STT provider takes an `STTConfig` (language settings) plus its credentials
and turns a chunk of audio into text. Nothing here depends on any web
framework, database, or this repo — only the standard library + httpx.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class STTConfig:
    """Transcription settings. Provider-agnostic; each provider uses what it can."""
    language_code: str = ""
    auto_language_detection: bool = False
    # free-form provider-specific overrides
    extra: dict = field(default_factory=dict)


@dataclass
class STTResult:
    """A transcription result."""
    text: str
    language: Optional[str] = None
    is_final: bool = True


class BaseSTTProvider(ABC):
    """
    Base class every provider implements.

    Concrete providers receive their credentials explicitly (api_key / base_url)
    so the module stays usable in any project.
    """

    def __init__(self, config: Optional[STTConfig] = None, **credentials):
        self.config = config or STTConfig()
        self.credentials = credentials

    @abstractmethod
    async def transcribe(self, audio: bytes, sample_rate: int = 16000) -> STTResult:
        """Transcribe a complete utterance of raw 16-bit PCM audio."""
        raise NotImplementedError
