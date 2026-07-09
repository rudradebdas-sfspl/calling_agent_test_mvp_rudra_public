"""
Sarvam TTS provider.

Credentials (passed in by the caller):
    api_key   -> Sarvam api-subscription-key

Model is hardcoded to "bulbul:v2". Sarvam returns base64-encoded WAV audio,
so this provider decodes it and yields WAV bytes in fixed-size chunks.
"""
from __future__ import annotations

import base64
from typing import AsyncIterator, Optional

from module.tts_core.base import BaseTTSProvider, OutputFormat, TTSConfig
from module.tts_core.errors import MissingCredentials
from module.tts_core.registry import register_provider
from module.tts_core.providers.sarvam.client import DEFAULT_TTS_URL, SarvamTTSClient
from module.tts_core.providers.sarvam.errors import SarvamTTSError
from module.tts_core.providers.sarvam.schemas import build_headers, build_tts_body

_CHUNK_SIZE = 4096


@register_provider("sarvam")
class SarvamTTSProvider(BaseTTSProvider):
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
            raise MissingCredentials("Sarvam requires an api_key")
        self._api_key = api_key
        self._client = SarvamTTSClient(base_url or DEFAULT_TTS_URL)
        self.output_format = OutputFormat("wav", "pcm_s16le", self.config.sample_rate)

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        body = build_tts_body(text, self.config)
        headers = build_headers(self._api_key)

        payload = await self._client.post(body, headers)

        audios = payload.get("audios") or []
        if not audios:
            raise SarvamTTSError("Sarvam TTS returned no audio")
        for b64_wav in audios:
            raw = base64.b64decode(b64_wav)
            for i in range(0, len(raw), _CHUNK_SIZE):
                yield raw[i:i + _CHUNK_SIZE]
