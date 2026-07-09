"""Base LLM/SLM provider interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    model: str
    temperature: float = 0.4
    max_tokens: int = 512
    extra: dict = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """
    All providers receive only NON-secret config (model name, temperature, etc).
    API keys / base URLs are read from env inside each concrete provider.
    """

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def generate(self, system_prompt: str, messages: list[dict]) -> str:
        """
        messages: [{"role": "user"|"assistant", "content": "..."}]
        Returns a single voice-friendly text answer.
        """
        raise NotImplementedError
