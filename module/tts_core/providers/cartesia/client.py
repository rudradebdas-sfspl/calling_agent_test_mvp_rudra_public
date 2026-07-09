"""Cartesia HTTP client — owns all network concerns for Cartesia TTS."""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import httpx

from module.tts_core.providers.cartesia.errors import CartesiaError

log = logging.getLogger("tts_core.cartesia")

DEFAULT_TTS_URL = "https://api.cartesia.ai/tts/bytes"
_MAX_RETRIES = 3
_RETRY_DELAY = 1.5
_TIMEOUT = 60


class CartesiaClient:
    """Thin async wrapper around the Cartesia /tts/bytes streaming endpoint."""

    def __init__(self, url: str | None = None):
        self._url = url or DEFAULT_TTS_URL

    async def stream(self, body: dict, headers: dict) -> AsyncIterator[bytes]:
        """POST `body` and yield raw audio byte chunks as they arrive."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    async with client.stream("POST", self._url, json=body, headers=headers) as resp:
                        resp.raise_for_status()
                        async for chunk in resp.aiter_bytes():
                            if chunk:
                                yield chunk
                return
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == _MAX_RETRIES:
                    raise CartesiaError(
                        f"Cartesia TTS failed after {_MAX_RETRIES} attempts: {exc}"
                    )
                log.warning(
                    "Cartesia connect error (%d/%d), retrying in %.1fs",
                    attempt, _MAX_RETRIES, _RETRY_DELAY,
                )
                await asyncio.sleep(_RETRY_DELAY)
            except httpx.HTTPStatusError as exc:
                raise CartesiaError(
                    f"Cartesia TTS HTTP {exc.response.status_code}: {exc.response.text}"
                )
