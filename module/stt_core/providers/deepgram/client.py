"""Deepgram STT HTTP client — owns the network call + error handling."""
from __future__ import annotations

import httpx

from module.stt_core.providers.deepgram.errors import DeepgramSTTError

DEFAULT_LISTEN_URL = "https://api.deepgram.com/v1/listen"
_TIMEOUT = 60


class DeepgramSTTClient:
    def __init__(self, url: str | None = None):
        self._url = url or DEFAULT_LISTEN_URL

    async def transcribe(self, *, headers: dict, params: dict, audio: bytes) -> dict:
        """POST raw audio and return the parsed JSON payload. Raises DeepgramSTTError."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(self._url, params=params, headers=headers, content=audio)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            raise DeepgramSTTError(
                f"Deepgram STT HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise DeepgramSTTError(f"Deepgram STT connection failed: {exc}") from exc
