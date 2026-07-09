from types import SimpleNamespace

import pytest

from module.stt_core.base import STTResult


class FakeSTT:
    async def transcribe(self, audio: bytes, sample_rate: int = 16000):
        assert audio
        assert sample_rate == 16000
        return STTResult(text="hello agent", language="en-IN")


class FakeLLM:
    async def generate(self, system_prompt: str, messages: list[dict]) -> str:
        assert "Reply in 1-3 short spoken sentences" in system_prompt
        assert messages[-1]["content"] == "hello agent"
        return "Hello, I can help."


class FakeTTS:
    def __init__(self):
        self.config = SimpleNamespace(language="en-IN", voice_id=None)

    async def synthesize(self, text: str):
        assert text == "Hello, I can help."
        yield b"audio-chunk-1"
        yield b"audio-chunk-2"


def _agent(**overrides):
    base = dict(
        id="00000000-0000-0000-0000-000000000001",
        system_prompt="You are an IT support voice agent.",
        kb_enabled=False,
        call_transfer_number=None,
        vad_mode="normal",
        stt_provider="sarvam",
        tts_provider="cartesia",
        llm_provider="gemini",
        llm_model="gemini-3.1-flash-lite",
        temperature=0.4,
        max_response_tokens=256,
        noise_cancellation_enabled=False,
        noise_cancellation_provider="quail",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_agent_pipeline_runs_one_full_turn_with_mocked_providers(monkeypatch):
    import backend.worker.agent_worker as worker

    monkeypatch.setattr(worker.STTProviderFactory, "create", lambda agent: FakeSTT())
    monkeypatch.setattr(worker.TTSProviderFactory, "create", lambda agent: FakeTTS())
    monkeypatch.setattr(worker, "build_llm_provider", lambda agent: FakeLLM())
    monkeypatch.setattr(worker, "build_noise_canceller", lambda agent: None)

    pipeline = worker.AgentPipeline(_agent(), session_id="ci-session")
    chunks = [chunk async for chunk in pipeline.handle_utterance(b"fake-pcm", 16000)]

    assert chunks == [b"audio-chunk-1", b"audio-chunk-2"]
    assert pipeline.history == [
        {"role": "user", "content": "hello agent"},
        {"role": "assistant", "content": "Hello, I can help."},
    ]