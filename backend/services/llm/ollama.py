"""
Local Ollama provider. Talks to OLLAMA_BASE_URL's /api/chat endpoint.
No API key needed for local Ollama.
"""
import httpx

from backend.config import settings
from backend.services.llm.base import BaseLLMProvider, LLMConfig


class OllamaProvider(BaseLLMProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._base_url = settings.OLLAMA_BASE_URL.rstrip("/")

    async def generate(self, system_prompt: str, messages: list[dict]) -> str:
        payload_messages = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.extend(messages)

        body = {
            "model": self.config.model or settings.OLLAMA_DEFAULT_MODEL,
            "messages": payload_messages,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
        return (data.get("message", {}).get("content") or "").strip()
