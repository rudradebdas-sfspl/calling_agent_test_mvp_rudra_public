from types import SimpleNamespace

import pytest


def _agent(**overrides):
    base = dict(
        stt_provider="sarvam",
        stt_language_code="bn-IN",
        stt_auto_language_detection=False,
        tts_provider="cartesia",
        cartesia_voice_id="voice-123",
        tts_language="bn-IN",
        tts_speed=1.1,
        tts_pitch=0.0,
        tts_volume=1.0,
        tts_emotion=None,
        tts_tone="friendly",
        tts_style_prompt=None,
        llm_provider="gemini",
        llm_model="gemini-3.1-flash-lite",
        temperature=0.3,
        max_response_tokens=256,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_stt_factory_maps_agent_config_without_real_api(monkeypatch):
    import backend.services.stt.factory as factory

    captured = {}

    def fake_create_provider(name, *, config=None, **credentials):
        captured["name"] = name
        captured["config"] = config
        captured["credentials"] = credentials
        return object()

    monkeypatch.setattr(factory, "create_provider", fake_create_provider)

    provider = factory.STTProviderFactory.create(_agent(stt_provider="sarvam"))

    assert provider is not None
    assert captured["name"] == "sarvam"
    assert captured["config"].language_code == "bn-IN"
    assert "api_key" in captured["credentials"]


def test_tts_factory_maps_agent_voice_and_tone_without_real_api(monkeypatch):
    import backend.services.tts.factory as factory

    captured = {}

    def fake_create_provider(name, *, config=None, **credentials):
        captured["name"] = name
        captured["config"] = config
        captured["credentials"] = credentials
        return object()

    monkeypatch.setattr(factory, "create_provider", fake_create_provider)

    provider = factory.TTSProviderFactory.create(_agent(tts_provider="cartesia"))

    assert provider is not None
    assert captured["name"] == "cartesia"
    assert captured["config"].voice_id == "voice-123"
    assert captured["config"].language == "bn-IN"
    assert captured["config"].tone == "friendly"
    assert captured["config"].sample_rate == 24000
    assert "api_key" in captured["credentials"]


def test_llm_factory_builds_gemini_provider_with_agent_config(monkeypatch):
    import backend.services.llm.factory as factory

    captured = {}

    class FakeGeminiProvider:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr(factory, "GeminiProvider", FakeGeminiProvider)

    provider = factory.build_llm_provider(_agent())

    assert isinstance(provider, FakeGeminiProvider)
    assert captured["config"].model == "gemini-3.1-flash-lite"
    assert captured["config"].temperature == 0.3
    assert captured["config"].max_tokens == 256


def test_unknown_tts_provider_fails_fast():
    import backend.services.tts.factory as factory

    with pytest.raises(ValueError):
        factory.TTSProviderFactory.create(_agent(tts_provider="not-real"))