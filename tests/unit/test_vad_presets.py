from types import SimpleNamespace

from backend.services.vad.presets import AGGRESSIVE, CUSTOM, NORMAL, resolve_vad_params


def test_normal_vad_preset_values():
    agent = SimpleNamespace(vad_mode=NORMAL)
    params = resolve_vad_params(agent)

    assert params.threshold == 0.50
    assert params.min_speech_ms == 250
    assert params.min_silence_ms == 700
    assert params.speech_pad_ms == 100


def test_aggressive_vad_preset_values():
    agent = SimpleNamespace(vad_mode=AGGRESSIVE)
    params = resolve_vad_params(agent)

    assert params.threshold == 0.40
    assert params.min_speech_ms == 200
    assert params.min_silence_ms == 500


def test_custom_vad_uses_agent_values():
    agent = SimpleNamespace(
        vad_mode=CUSTOM,
        vad_threshold=0.42,
        vad_min_speech_ms=180,
        vad_min_silence_ms=450,
        vad_speech_pad_ms=90,
    )

    params = resolve_vad_params(agent)

    assert params.threshold == 0.42
    assert params.min_speech_ms == 180
    assert params.min_silence_ms == 450
    assert params.speech_pad_ms == 90