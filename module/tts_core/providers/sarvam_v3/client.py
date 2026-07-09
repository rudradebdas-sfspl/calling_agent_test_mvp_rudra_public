"""
Sarvam v3 REST client — fallback transport.

Uses a persistent httpx.AsyncClient (connection pooling) instead of opening a
new TCP+TLS connection per call, which was adding 50-150ms to every REST
fallback request.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from module.tts_core.providers.sarvam_v3.errors import SarvamV3TTSError

log = logging.getLogger("tts_core.sarvam_v3")

DEFAULT_REST_URL = "https://api.sarvam.ai/text-to-speech"
_MAX_RETRIES = 3
_RETRY_DELAY = 1.5
_TIMEOUT = 60


class SarvamV3RestClient:

    def __init__(self, url: str | None = None):
        self._url = url or DEFAULT_REST_URL
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=_TIMEOUT,
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            )
        return self._client

    async def post(self, body: dict, headers: dict) -> dict:
        client = self._get_client()
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await client.post(self._url, json=body, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as exc:
                raise SarvamV3TTSError(
                    f"Sarvam v3 REST HTTP {exc.response.status_code}: {exc.response.text}"
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == _MAX_RETRIES:
                    raise SarvamV3TTSError(
                        f"Sarvam v3 REST failed after {_MAX_RETRIES} attempts: {exc}"
                    )
                log.warning("REST error (%d/%d), retrying", attempt, _MAX_RETRIES)
                await asyncio.sleep(_RETRY_DELAY)
        return {}

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
