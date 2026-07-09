"""
Quail (ai-coustics) constants + pure helpers.

The model id is HARDCODED here so anyone importing this module gets a working
denoiser without writing a single line of config. The SDK *license* is a secret
and is NOT hardcoded — it is read from the environment (or passed in by the
caller), so the key never ships inside the source.
"""
from __future__ import annotations

import os

import numpy as np

# ── HARDCODED model (no config needed to use the module) ─────────────
DEFAULT_MODEL_ID = "quail-vf-2.1-l-16khz"

# ── Default tuning (overridable via NoiseCancellationConfig or env) ──
DEFAULT_ENHANCEMENT_LEVEL = 1.0
DEFAULT_DRY_MIX = 0.0
DEFAULT_MIN_ENERGY_RATIO = 0.18
DEFAULT_ENERGY_FLOOR = 0.002
DEFAULT_MODEL_DIR = "./models"

# Conservative native-config fallbacks if SDK probing fails.
FALLBACK_NATIVE_SR = 16000
FALLBACK_NUM_FRAMES = 160


def license_key(explicit: str | None = None) -> str:
    """Resolve the Quail SDK license: explicit arg > AIC_SDK_LICENSE > QUAIL_SDK_KEY."""
    return (
        (explicit or "").strip()
        or os.getenv("AIC_SDK_LICENSE", "").strip()
        or os.getenv("QUAIL_SDK_KEY", "").strip()
    )


def env_enabled() -> bool:
    """
    Back-compat toggle. Enabled unless ENABLE_QUAIL is explicitly false, or the
    legacy ENABLE_DEEPFILTER=false is set.
    """
    enable_quail = os.getenv("ENABLE_QUAIL", "true").strip().lower() in ("true", "1", "yes")
    legacy_off = os.getenv("ENABLE_DEEPFILTER", "true").strip().lower() in ("false", "0", "no")
    return enable_quail and not legacy_off


def clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def resample(audio: np.ndarray, from_sr: int, to_sr: int) -> np.ndarray:
    """Simple linear-interpolation resampling."""
    if from_sr == to_sr or audio.size == 0:
        return audio.astype(np.float32, copy=False)
    ratio = to_sr / from_sr
    n_out = max(1, int(round(len(audio) * ratio)))
    indices = np.linspace(0, len(audio) - 1, n_out)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)
