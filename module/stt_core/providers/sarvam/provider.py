"""
Sarvam STT provider.

Credentials (passed in by the caller):
    api_key   -> Sarvam api-subscription-key

Raw 16-bit PCM is wrapped in a WAV container and posted as a file upload.
No model is sent — Sarvam uses its API default.
"""
from __future__ import annotations

from typing import Optional

from module.stt_core.base import BaseSTTProvider, STTConfig, STTResult
from module.stt_core.errors import MissingCredentials
from module.stt_core.registry import register_provider
from module.stt_core.providers.sarvam.client import DEFAULT_STT_URL, SarvamSTTClient
from module.stt_core.providers.sarvam.schemas import build_headers, build_multipart, parse_response, resolve_language


@register_provider("sarvam")
class SarvamSTTProvider(BaseSTTProvider):
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
            raise MissingCredentials("Sarvam requires an api_key")
        self._api_key = api_key
        self._client = SarvamSTTClient(base_url or DEFAULT_STT_URL)

    async def transcribe(self, audio: bytes, sample_rate: int = 16000) -> STTResult:
        language = resolve_language(self.config)
        files, data = build_multipart(audio, sample_rate, self.config)
        headers = build_headers(self._api_key)

        payload = await self._client.transcribe(headers=headers, files=files, data=data)
        text, detected = parse_response(payload, language)
        return STTResult(text=text, language=detected, is_final=True)
