"""
LLM factory. Maps the agent's `llm_provider` string to a concrete provider.
This is the single place the pipeline calls — nothing is hardcoded to one LLM.
"""
from backend.config import settings
from backend.services.llm.base import BaseLLMProvider, LLMConfig
from backend.services.llm.gemini import GeminiProvider
from backend.services.llm.ollama import OllamaProvider
from backend.services.llm.openai_compatible import OpenAICompatibleProvider

_DEFAULT_MODELS = {
    "gemini": lambda: settings.GEMINI_DEFAULT_MODEL,
    "openai-compatible": lambda: settings.OPENAI_COMPATIBLE_DEFAULT_MODEL,
    "local-ollama": lambda: settings.OLLAMA_DEFAULT_MODEL,
}


def build_llm_provider(agent) -> BaseLLMProvider:
    provider = agent.llm_provider
    model = agent.llm_model or _DEFAULT_MODELS.get(provider, lambda: "")()
    config = LLMConfig(
        model=model,
        temperature=agent.temperature,
        max_tokens=agent.max_response_tokens,
    )

    if provider == "gemini":
        return GeminiProvider(config)
    if provider == "openai-compatible":
        return OpenAICompatibleProvider(config)
    if provider == "local-ollama":
        return OllamaProvider(config)
    if provider == "sarvam-slm":
        # Reserved for when Sarvam SLM is available. Sarvam exposes an
        # OpenAI-compatible surface, so it can route through that provider once
        # SARVAM SLM env vars are wired in.
        raise NotImplementedError("sarvam-slm provider is not available yet")

    raise ValueError(f"Unknown llm_provider: {provider}")
