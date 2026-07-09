"""
Quail SDK transport: model loading (singleton) + per-session processor creation.

The model is loaded ONCE and shared across all call sessions. Each session gets
its own Processor (sharing the model weights). The aic_sdk import is lazy so the
rest of the system boots even when the SDK isn't installed — in that case the
provider falls back to audio passthrough and never breaks the call.
"""
from __future__ import annotations

import logging
import os
import time

from module.noise_cancellation_core.providers.quail import schemas

logger = logging.getLogger("noise_cancellation.quail")

# ── module-level singleton state ─────────────────────────────
_aic = None
_model = None
_model_sr: int = schemas.FALLBACK_NATIVE_SR
_model_num_frames: int = schemas.FALLBACK_NUM_FRAMES
_model_loaded = False
_model_load_attempted = False


def is_model_loaded() -> bool:
    return _model_loaded


def native_config() -> tuple[int, int]:
    """(sample_rate, num_frames) of the loaded model."""
    return _model_sr, _model_num_frames


def load_model(model_id: str, model_path: str | None, model_dir: str, license_key_value: str) -> bool:
    """Load the Quail model once. Returns True if Quail is usable."""
    global _aic, _model, _model_sr, _model_num_frames, _model_loaded, _model_load_attempted

    if _model_load_attempted:
        return _model_loaded
    _model_load_attempted = True

    if not license_key_value:
        logger.error("[Quail] No license key (set AIC_SDK_LICENSE) — audio passthrough")
        return False

    try:
        t0 = time.time()
        import aic_sdk as aic  # noqa: F401

        if model_path and os.path.exists(model_path):
            model = aic.Model.from_file(model_path)
            src = model_path
        else:
            os.makedirs(model_dir, exist_ok=True)
            downloaded = aic.Model.download(model_id, model_dir)
            model = aic.Model.from_file(downloaded)
            src = f"{model_id} -> {downloaded}"

        _aic = aic
        _model = model
        _model_loaded = True

        try:
            probe = aic.ProcessorConfig.optimal(model, num_channels=1, allow_variable_frames=True)
            _model_sr = int(getattr(probe, "sample_rate", schemas.FALLBACK_NATIVE_SR) or schemas.FALLBACK_NATIVE_SR)
            _model_num_frames = int(getattr(probe, "num_frames", schemas.FALLBACK_NUM_FRAMES) or schemas.FALLBACK_NUM_FRAMES)
        except Exception:
            _model_sr = schemas.FALLBACK_NATIVE_SR
            _model_num_frames = schemas.FALLBACK_NUM_FRAMES

        logger.info(
            "[Quail] OK loaded (%s) native_sr=%dHz block=%d frames in %.1fs",
            src, _model_sr, _model_num_frames, time.time() - t0,
        )
        return True

    except ImportError as e:
        logger.warning("[Quail] aic-sdk not installed: %s — audio passthrough", e)
        return False
    except Exception as e:
        logger.error("[Quail] Failed to load model: %s — audio passthrough", e)
        return False


def make_processor(license_key_value: str, enhancement_level: float):
    """
    Create a per-session Processor on the shared model.
    Returns (processor, sample_rate, num_frames) or (None, sr, frames) on failure.
    """
    if not _model_loaded or _aic is None:
        return None, _model_sr, _model_num_frames
    try:
        cfg = _aic.ProcessorConfig.optimal(_model, num_channels=1, allow_variable_frames=True)
        sr = int(getattr(cfg, "sample_rate", _model_sr) or _model_sr)
        nf = int(getattr(cfg, "num_frames", _model_num_frames) or _model_num_frames)
        processor = _aic.Processor(_model, license_key_value, cfg)
        _try_set_enhancement_level(processor, enhancement_level)
        return processor, sr, nf
    except Exception as e:
        logger.error("[Quail] Processor init failed: %s — audio passthrough", e)
        return None, _model_sr, _model_num_frames


def process_block(processor, buf):
    """Run the Quail processor on one float32 (1, N) block. Returns the SDK output."""
    return processor.process(buf)


def _try_set_enhancement_level(processor, level: float):
    """Best-effort: the control API differs across SDK versions; never fail the call."""
    if processor is None:
        return
    try:
        param = None
        if hasattr(_aic, "AICParameter") and hasattr(_aic.AICParameter, "ENHANCEMENT_LEVEL"):
            param = _aic.AICParameter.ENHANCEMENT_LEVEL
        if param is not None and hasattr(processor, "set_parameter"):
            processor.set_parameter(param, float(level))
            return
        if hasattr(processor, "get_processor_context"):
            ctx = processor.get_processor_context()
            if param is not None and hasattr(ctx, "set_parameter"):
                ctx.set_parameter(param, float(level))
    except Exception as e:
        logger.debug("[Quail] enhancement-level set skipped: %s", e)
