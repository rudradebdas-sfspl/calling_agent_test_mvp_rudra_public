"""
Cartesia TTS provider.

Credentials (passed in by the caller):
    api_key   -> Cartesia X-API-Key

Model is hardcoded to "sonic-3". Output: raw PCM s16le at config.sample_rate
(default 24000 Hz), streamed.
"""
from __future__ import annotations

from typing import AsyncIterator, Optional

from module.tts_core.base import BaseTTSProvider, OutputFormat, TTSConfig
from module.tts_core.errors import MissingCredentials
from module.tts_core.registry import register_provider
from module.tts_core.providers.cartesia.client import DEFAULT_TTS_URL, CartesiaClient
from module.tts_core.providers.cartesia.mapper import map_tone_to_cartesia, resolve_voice_id
from module.tts_core.providers.cartesia.schemas import build_headers, build_transcript, build_tts_body

_MODEL = "sonic-3"


@register_provider("cartesia")
class CartesiaTTSProvider(BaseTTSProvider):
    def __init__(
        self,
        config: Optional[TTSConfig] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **extra,
    ):
        super().__init__(config, api_key=api_key, **extra)
        if not api_key:
            raise MissingCredentials("Cartesia requires an api_key")
        self._api_key = api_key
        self._client = CartesiaClient(base_url or DEFAULT_TTS_URL)
        self.output_format = OutputFormat("raw", "pcm_s16le", self.config.sample_rate)

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        voice_id = resolve_voice_id(self.config)
        controls = map_tone_to_cartesia(self.config)

        body = build_tts_body(
            model=_MODEL,
            transcript=build_transcript(text, controls),
            voice_id=voice_id,
            language=self.config.language,
            sample_rate=self.config.sample_rate,
            controls=controls,
        )
        headers = build_headers(self._api_key)

        async for chunk in self._client.stream(body, headers):
            yield chunk
