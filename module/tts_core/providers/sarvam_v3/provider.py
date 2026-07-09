"""
Sarvam Bulbul v3 TTS provider.

Model hardcoded: "bulbul:v3" (in schemas.py). Factory only passes api_key.

Transport:
    1. WebSocket (default)  → persistent low-latency streaming
    2. REST (fallback)      → used if WebSocket is unavailable or fails

WebSocket is disabled for the rest of this provider's lifetime (falls back to
REST from then on) if the `websockets` package is missing or DNS resolution
fails — both are permanent until the process/network changes, so retrying
them on every call would just add latency for no benefit. Any other WS error
(timeouts, a single bad connection) is treated as transient and WebSocket is
retried on the next call.
"""
from __future__ import annotations

import base64
import logging
from typing import AsyncIterator, Optional

from module.tts_core.base import BaseTTSProvider, OutputFormat, TTSConfig
from module.tts_core.errors import MissingCredentials
from module.tts_core.registry import register_provider
from module.tts_core.providers.sarvam_v3.audio import coerce_to_pcm
from module.tts_core.providers.sarvam_v3.client import SarvamV3RestClient
from module.tts_core.providers.sarvam_v3.errors import SarvamV3TTSError
from module.tts_core.providers.sarvam_v3.schemas import build_headers, build_tts_body, build_ws_config
from module.tts_core.providers.sarvam_v3.ws_client import SarvamV3WebSocketClient

log = logging.getLogger("tts_core.sarvam_v3")
_CHUNK_SIZE = 4096
_PERMANENT_WS_FAILURE_MARKERS = ("websockets package not installed", "DNS resolution failed")


@register_provider("sarvam-v3")
class SarvamV3TTSProvider(BaseTTSProvider):
    def __init__(
        self,
        config: Optional[TTSConfig] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        use_websocket: bool = True,
        temperature: Optional[float] = None,
        **extra,
    ):
        super().__init__(config, api_key=api_key, **extra)
        if not api_key:
            raise MissingCredentials("Sarvam v3 requires an api_key")
        self._api_key = api_key
        self._use_websocket = use_websocket
        self._temperature = temperature
        self._ws_client = SarvamV3WebSocketClient(api_key=api_key, ws_url=ws_url)
        self._rest_client = SarvamV3RestClient(url=base_url)
        self._ws_disabled = False  # set permanently once WS proves unusable
        # Bytes yielded are raw PCM (coerce_to_pcm runs on every chunk before
        # it's handed to the caller), so "raw" is the honest declaration here
        # — same convention Cartesia's provider uses.
        self.output_format = OutputFormat("raw", "pcm_s16le", self.config.sample_rate)

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        if self._use_websocket and not self._ws_disabled:
            yielded_any = False
            try:
                async for chunk in self._synthesize_ws(text):
                    yielded_any = True
                    yield chunk
                return
            except SarvamV3TTSError as exc:
                if any(marker in str(exc) for marker in _PERMANENT_WS_FAILURE_MARKERS):
                    self._ws_disabled = True
                    log.warning("Sarvam v3 WebSocket permanently disabled (%s) — using REST", exc)
                else:
                    log.warning("Sarvam v3 WebSocket failed (%s) — falling back to REST", exc)

                if yielded_any:
                    # Some audio for this utterance already reached the caller;
                    # restarting via REST now would replay the start of the
                    # sentence. Surface the error instead of risking that.
                    log.error("Sarvam v3 WebSocket failed mid-stream after yielding audio")
                    raise

        async for chunk in self._synthesize_rest(text):
            yield chunk

    async def _synthesize_ws(self, text: str) -> AsyncIterator[bytes]:
        config_msg = build_ws_config(self.config)
        async for chunk in self._ws_client.synthesize_stream(text, config_msg, self.config.sample_rate):
            yield chunk

    async def _synthesize_rest(self, text: str) -> AsyncIterator[bytes]:
        body = build_tts_body(text, self.config, temperature=self._temperature)
        headers = build_headers(self._api_key)
        payload = await self._rest_client.post(body, headers)

        audios = payload.get("audios") or []
        if not audios:
            raise SarvamV3TTSError("Sarvam v3 REST returned no audio")
        for b64_wav in audios:
            pcm = coerce_to_pcm(base64.b64decode(b64_wav), self.config.sample_rate)
            for i in range(0, len(pcm), _CHUNK_SIZE):
                yield pcm[i : i + _CHUNK_SIZE]

    async def close(self) -> None:
        await self._rest_client.close()
