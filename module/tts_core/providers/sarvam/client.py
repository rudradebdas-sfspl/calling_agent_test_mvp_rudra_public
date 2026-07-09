"""Sarvam HTTP client — owns network concerns for Sarvam TTS."""
from __future__ import annotations

import asyncio
import logging

import httpx

from module.tts_core.providers.sarvam.errors import SarvamTTSError

log = logging.getLogger("tts_core.sarvam")

DEFAULT_TTS_URL = "https://api.sarvam.ai/text-to-speech"
_MAX_RETRIES = 3
_RETRY_DELAY = 1.5
_TIMEOUT = 60


class SarvamTTSClient:
    def __init__(self, url: str | None = None):
        self._url = url or DEFAULT_TTS_URL

    async def post(self, body: dict, headers: dict) -> dict:
        """POST and return the parsed JSON payload. Raises SarvamTTSError."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    resp = await client.post(self._url, json=body, headers=headers)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                raise SarvamTTSError(
                    f"Sarvam TTS HTTP {exc.response.status_code}: {exc.response.text}"
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == _MAX_RETRIES:
                    raise SarvamTTSError(
                        f"Sarvam TTS failed after {_MAX_RETRIES} attempts: {exc}"
                    )
                log.warning(
                    "Sarvam connect error (%d/%d), retrying in %.1fs",
                    attempt, _MAX_RETRIES, _RETRY_DELAY,
                )
                await asyncio.sleep(_RETRY_DELAY)
        return {}
