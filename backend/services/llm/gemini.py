"""
Gemini provider. Reads GEMINI_API_KEY from env. Model name comes from the agent
config (falls back to GEMINI_DEFAULT_MODEL).

NOTE: SDK call shape may differ slightly across `google-genai` versions; the
mapping is isolated here so swapping SDK versions touches only this file.
"""
from backend.config import settings
from backend.services.llm.base import BaseLLMProvider, LLMConfig


class GeminiProvider(BaseLLMProvider):
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set in .env")
        # Imported lazily so the app boots even if the SDK isn't installed.
        from google import genai  # pip install google-genai

        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def generate(self, system_prompt: str, messages: list[dict]) -> str:
        from google.genai import types

        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]
        resp = await self._client.aio.models.generate_content(
            model=self.config.model or settings.GEMINI_DEFAULT_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt or None,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_tokens,
            ),
        )
        return (resp.text or "").strip()
