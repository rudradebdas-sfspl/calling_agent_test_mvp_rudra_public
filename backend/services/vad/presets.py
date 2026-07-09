"""
VAD presets. Maps a friendly `vad_mode` to concrete Silero parameters.

Silero VAD is used ONLY for speech detection and turn detection.
No noise cancellation is performed anywhere (no Krisp / DeepFilter / Quail / RNNoise).
"""
from dataclasses import dataclass

LOW_SENSITIVITY = "low_sensitivity"
NORMAL = "normal"
AGGRESSIVE = "aggressive"
VERY_AGGRESSIVE = "very_aggressive"
CUSTOM = "custom"

VAD_MODES = [LOW_SENSITIVITY, NORMAL, AGGRESSIVE, VERY_AGGRESSIVE, CUSTOM]


@dataclass(frozen=True)
class VADParams:
    threshold: float
    min_speech_ms: int
    min_silence_ms: int
    speech_pad_ms: int = 100


# Preset table straight from the spec.
PRESETS: dict[str, VADParams] = {
    LOW_SENSITIVITY: VADParams(threshold=0.65, min_speech_ms=350, min_silence_ms=900),
    NORMAL: VADParams(threshold=0.50, min_speech_ms=250, min_silence_ms=700),
    AGGRESSIVE: VADParams(threshold=0.99, min_speech_ms=200, min_silence_ms=500),
    VERY_AGGRESSIVE: VADParams(threshold=0.35, min_speech_ms=150, min_silence_ms=400),
}

PRESET_NOTES: dict[str, str] = {
    LOW_SENSITIVITY: "Best for noisy rooms where false speech detection must be avoided.",
    NORMAL: "Best default mode for normal office/browser mic calls.",
    AGGRESSIVE: "Faster response, but may detect more background speech.",
    VERY_AGGRESSIVE: "Fastest turn detection for low-latency demos; risky in noisy rooms.",
    CUSTOM: "Manually set threshold, min speech/silence duration, and padding.",
}


def resolve_vad_params(agent) -> VADParams:
    """
    Given an agent (model or schema with vad_* attributes), return the effective
    VAD parameters the worker should feed to Silero.

    - For a preset mode, the preset values win (the stored threshold columns are
      kept in sync on save, but the preset is the source of truth at runtime).
    - For `custom`, the per-agent stored values are used as-is.
    """
    mode = getattr(agent, "vad_mode", NORMAL)
    if mode in PRESETS:
        return PRESETS[mode]
    return VADParams(
        threshold=getattr(agent, "vad_threshold", 0.5),
        min_speech_ms=getattr(agent, "vad_min_speech_ms", 250),
        min_silence_ms=getattr(agent, "vad_min_silence_ms", 700),
        speech_pad_ms=getattr(agent, "vad_speech_pad_ms", 100),
    )
