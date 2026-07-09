"""
OpenAI-compatible provider. Works with any server exposing the OpenAI
chat-completions API (vLLM, LM Studio, Together, Groq, etc.).

Uses OPENAI_COMPATIBLE_BASE_URL + OPENAI_COMPATIBLE_API_KEY from env.
"""
from backend.config import settings
from backend.services.llm.base import BaseLLMProvider, LLMConfig


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not settings.OPENAI_COMPATIBLE_BASE_URL:
            raise RuntimeError("OPENAI_COMPATIBLE_BASE_URL is not set in .env")
        from openai import AsyncOpenAI  # pip install openai

        self._client = AsyncOpenAI(
            api_key=settings.OPENAI_COMPATIBLE_API_KEY or "not-needed",
            base_url=settings.OPENAI_COMPATIBLE_BASE_URL,
        )

    async def generate(self, system_prompt: str, messages: list[dict]) -> str:
        payload = []
        if system_prompt:
            payload.append({"role": "system", "content": system_prompt})
        payload.extend(messages)
        resp = await self._client.chat.completions.create(
            model=self.config.model or settings.OPENAI_COMPATIBLE_DEFAULT_MODEL,
            messages=payload,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
