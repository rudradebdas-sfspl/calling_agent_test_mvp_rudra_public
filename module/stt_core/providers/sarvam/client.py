"""Sarvam STT HTTP client — owns the network call + error handling."""
from __future__ import annotations

import httpx

from module.stt_core.providers.sarvam.errors import SarvamSTTError

DEFAULT_STT_URL = "https://api.sarvam.ai/speech-to-text"
_TIMEOUT = 60


class SarvamSTTClient:
    def __init__(self, url: str | None = None):
        self._url = url or DEFAULT_STT_URL

    async def transcribe(self, *, headers: dict, files: dict, data: dict) -> dict:
        """POST the audio and return the parsed JSON payload. Raises SarvamSTTError."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(self._url, headers=headers, files=files, data=data)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            raise SarvamSTTError(
                f"Sarvam STT HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise SarvamSTTError(f"Sarvam STT connection failed: {exc}") from exc
