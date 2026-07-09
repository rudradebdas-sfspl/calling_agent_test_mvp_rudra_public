import pytest
from pydantic import ValidationError

from backend.schemas.agent import AgentCreate


def test_agent_create_normalizes_vad_preset_values():
    payload = AgentCreate(name="CI Agent", vad_mode="aggressive", vad_threshold=0.99)

    assert payload.vad_threshold == 0.40
    assert payload.vad_min_speech_ms == 200
    assert payload.vad_min_silence_ms == 500


def test_agent_create_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        AgentCreate(name="Bad Agent", stt_provider="unknown-stt")


def test_agent_create_rejects_invalid_tts_tone():
    with pytest.raises(ValidationError):
        AgentCreate(name="Bad Tone", tts_tone="super-angry-mode")