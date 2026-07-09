"""
Core contracts for tts_core.

A TTS provider takes a `TTSConfig` (voice + style settings) plus its credentials
and turns text into a stream of audio bytes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


@dataclass
class TTSConfig:
    """Voice + style settings. Provider-agnostic; each provider uses what it can."""
    voice_id: Optional[str] = None
    language: str = "en"
    speed: float = 1.0
    pitch: float = 0.0
    volume: float = 1.0
    emotion: Optional[str] = None
    tone: str = "neutral"
    style_prompt: Optional[str] = None
    sample_rate: int = 24000
    # free-form provider-specific overrides
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OutputFormat:
    """Describes the audio bytes a provider yields, so consumers can decode them."""
    container: str      # "raw" | "wav"
    encoding: str       # "pcm_s16le" | ...
    sample_rate: int


class BaseTTSProvider(ABC):
    """
    Base class every provider implements.

    Concrete providers receive their credentials explicitly (api_key/base_url/...)
    so the module stays usable in any project. They expose:
      - output_format : what the yielded bytes are
      - synthesize()  : async stream of audio bytes
    """

    #: providers override this to advertise their output bytes
    output_format: OutputFormat = OutputFormat("raw", "pcm_s16le", 24000)

    def __init__(self, config: Optional[TTSConfig] = None, **credentials):
        self.config = config or TTSConfig()
        self.credentials = credentials

    @abstractmethod
    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Yield audio byte chunks for `text` (see `output_format`)."""
        raise NotImplementedError
        yield b""  # pragma: no cover

    async def synthesize_all(self, text: str) -> bytes:
        """Convenience: collect the whole stream into one bytes object."""
        out = bytearray()
        async for chunk in self.synthesize(text):
            out.extend(chunk)
        return bytes(out)
