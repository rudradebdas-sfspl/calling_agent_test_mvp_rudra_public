"""
Deepgram STT provider.

Credentials (passed in by the caller):
    api_key   -> Deepgram API key

Model is hardcoded to "nova-3". Raw 16-bit PCM (linear16) is posted directly.
When config.auto_language_detection is True, Deepgram's detect_language is used.
"""
from __future__ import annotations

from typing import Optional

from module.stt_core.base import BaseSTTProvider, STTConfig, STTResult
from module.stt_core.errors import MissingCredentials
from module.stt_core.registry import register_provider
from module.stt_core.providers.deepgram.client import DEFAULT_LISTEN_URL, DeepgramSTTClient
from module.stt_core.providers.deepgram.schemas import build_headers, build_params, parse_response


@register_provider("deepgram")
class DeepgramSTTProvider(BaseSTTProvider):
    def __init__(
        self,
        config: Optional[STTConfig] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **extra,
    ):
        super().__init__(config, api_key=api_key, **extra)
        if not api_key:
            raise MissingCredentials("Deepgram requires an api_key")
        self._api_key = api_key
        self._client = DeepgramSTTClient(base_url or DEFAULT_LISTEN_URL)

    async def transcribe(self, audio: bytes, sample_rate: int = 16000) -> STTResult:
        params = build_params(self.config, sample_rate)
        headers = build_headers(self._api_key)

        payload = await self._client.transcribe(headers=headers, params=params, audio=audio)
        text, detected = parse_response(payload, self.config, params)
        return STTResult(text=text, language=detected, is_final=True)
