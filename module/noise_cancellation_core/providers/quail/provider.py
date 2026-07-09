"""
Quail (ai-coustics) real-time speech-enhancement provider.

Primary-speaker isolation: suppresses background human voices / noise while
preserving the phonetic structure STT relies on. Same streaming contract as the
rest of the pipeline, so the worker needs no structural changes:

    .is_active            -> bool
    .process_frame(frame) -> list[AudioFrame]
    .flush()              -> list[AudioFrame]
    .stats()              -> dict

`DeepFilterDenoiser` is kept as an alias for backwards-compat.

Credentials:
    license_key  -> Quail SDK key (optional here; falls back to AIC_SDK_LICENSE /
                    QUAIL_SDK_KEY in the environment).
Model:
    Hardcoded to schemas.DEFAULT_MODEL_ID unless config.model_id overrides it.

Fallback: if the SDK / model / license fails to load, audio passes through
unchanged so a call is NEVER broken by the denoiser.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np

from module.noise_cancellation_core.base import BaseNoiseCanceller, NoiseCancellationConfig
from module.noise_cancellation_core.registry import register_provider
from module.noise_cancellation_core.providers.quail import client, schemas

logger = logging.getLogger("noise_cancellation.quail")


@register_provider("quail")
class QuailNoiseCanceller(BaseNoiseCanceller):
    def __init__(
        self,
        config: Optional[NoiseCancellationConfig] = None,
        *,
        license_key: Optional[str] = None,
        **extra,
    ):
        super().__init__(config, license_key=license_key, **extra)

        self._license = schemas.license_key(license_key)
        self._model_id = self.config.model_id or schemas.DEFAULT_MODEL_ID
        self._enhancement = schemas.clamp(self.config.enhancement_level, 0.0, 1.0)
        self._dry_mix = schemas.clamp(self.config.dry_mix, 0.0, 0.4)
        self._min_energy_ratio = schemas.clamp(self.config.min_energy_ratio, 0.05, 0.95)
        self._energy_floor = max(1e-6, self.config.energy_floor)

        # Respect the disabled flag (and the legacy ENABLE_QUAIL/ENABLE_DEEPFILTER env).
        want = self.config.enabled and schemas.env_enabled()
        self._enabled = want and client.load_model(
            self._model_id, self.config.model_path, self.config.model_dir, self._license
        )

        # per-session processor (shares the global model weights)
        self._processor = None
        self._proc_sr, self._proc_num_frames = client.native_config()

        # streaming buffers
        self._in_f32 = np.zeros(0, dtype=np.float32)   # model-rate mono awaiting a block
        self._out_bytes = bytearray()                  # original-rate int16 awaiting framing

        # frame template
        self._src_sr: int = 0
        self._src_channels: int = 1
        self._frame_byte_size: int = 0
        self._last_template_frame = None

        # stats
        self._frames_processed = 0
        self._total_latency_ms = 0.0

        if self._enabled:
            proc, sr, nf = client.make_processor(self._license, self._enhancement)
            self._processor = proc
            self._proc_sr, self._proc_num_frames = sr, nf
            if proc is None:
                self._enabled = False

    # ── status ──
    @property
    def is_active(self) -> bool:
        return bool(self._enabled and client.is_model_loaded() and self._processor is not None)

    # ── main entry point ──
    def process_frame(self, frame) -> list:
        if not self.is_active:
            return [frame]
        try:
            sr = int(getattr(frame, "sample_rate", schemas.FALLBACK_NATIVE_SR) or schemas.FALLBACK_NATIVE_SR)
            channels = int(getattr(frame, "num_channels", 1) or 1)
            raw = bytes(getattr(frame, "data", b"") or b"")
            if not raw:
                return [frame]

            self._last_template_frame = frame

            if not self._src_sr:
                self._src_sr, self._src_channels, self._frame_byte_size = sr, channels, len(raw)
            elif self._src_sr != sr or self._src_channels != channels:
                self._in_f32 = np.zeros(0, dtype=np.float32)
                self._out_bytes = bytearray()
                self._src_sr, self._src_channels, self._frame_byte_size = sr, channels, len(raw)

            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if channels > 1:
                audio = audio.reshape(-1, channels).mean(axis=1)

            if sr != self._proc_sr:
                audio = schemas.resample(audio, sr, self._proc_sr)

            self._in_f32 = np.concatenate([self._in_f32, audio]) if self._in_f32.size else audio

            n = self._proc_num_frames
            while len(self._in_f32) >= n:
                block = self._in_f32[:n]
                self._in_f32 = self._in_f32[n:]
                self._append_enhanced(block, sr)

            return self._drain_frames(emit_partial=False)

        except Exception as e:
            logger.debug("[Quail] Frame error: %s — passthrough", e)
            self._in_f32 = np.zeros(0, dtype=np.float32)
            return [frame]

    def flush(self) -> list:
        if not self.is_active:
            self._in_f32 = np.zeros(0, dtype=np.float32)
            self._out_bytes = bytearray()
            return []
        try:
            if self._in_f32.size:
                self._append_enhanced(self._in_f32, self._src_sr or self._proc_sr)
                self._in_f32 = np.zeros(0, dtype=np.float32)
            return self._drain_frames(emit_partial=True)
        except Exception:
            self._in_f32 = np.zeros(0, dtype=np.float32)
            self._out_bytes = bytearray()
            return []

    # ── internals ──
    def _append_enhanced(self, block_f32: np.ndarray, out_sr: int):
        t0 = time.time()
        dry_ref = block_f32.astype(np.float32, copy=True)

        buf = np.ascontiguousarray(block_f32.reshape(1, -1), dtype=np.float32)
        out = client.process_block(self._processor, buf)
        enhanced = np.asarray(out, dtype=np.float32).reshape(-1) if out is not None else buf.reshape(-1)

        if self._dry_mix > 0 and len(enhanced) == len(dry_ref):
            enhanced = (1.0 - self._dry_mix) * enhanced + self._dry_mix * dry_ref

        # Guardrail: never let enhancement wipe the caller's voice (protects STT recall).
        if dry_ref.size and enhanced.size == dry_ref.size:
            dry_rms = float(np.sqrt(np.mean(np.square(dry_ref))))
            enh_rms = float(np.sqrt(np.mean(np.square(enhanced))))
            if dry_rms >= self._energy_floor:
                ratio = enh_rms / max(dry_rms, 1e-8)
                if ratio < self._min_energy_ratio:
                    enhanced = 0.35 * enhanced + 0.65 * dry_ref

        if out_sr and out_sr != self._proc_sr:
            enhanced = schemas.resample(enhanced, self._proc_sr, out_sr)

        pcm16 = np.clip(enhanced * 32768.0, -32768, 32767).astype(np.int16)
        self._out_bytes.extend(pcm16.tobytes())

        self._frames_processed += 1
        self._total_latency_ms += (time.time() - t0) * 1000.0

    def _drain_frames(self, emit_partial: bool) -> list:
        from livekit import rtc

        size = self._frame_byte_size or len(self._out_bytes)
        if size <= 0:
            return []

        frames = []
        while len(self._out_bytes) >= size:
            chunk = bytes(self._out_bytes[:size])
            del self._out_bytes[:size]
            frames.append(self._make_frame(rtc, chunk))

        if emit_partial and self._out_bytes:
            chunk = bytes(self._out_bytes) + b"\x00" * (size - len(self._out_bytes))
            del self._out_bytes[:]
            frames.append(self._make_frame(rtc, chunk))

        return [f for f in frames if f is not None]

    def _make_frame(self, rtc, chunk: bytes):
        try:
            ch = max(1, self._src_channels)
            spc = max(1, len(chunk) // (2 * ch))
            return rtc.AudioFrame(
                data=chunk,
                sample_rate=self._src_sr or self._proc_sr,
                num_channels=ch,
                samples_per_channel=spc,
            )
        except Exception:
            try:
                tpl = self._last_template_frame
                ch = int(getattr(tpl, "num_channels", 1) or 1)
                spc = max(1, len(chunk) // (2 * ch))
                return rtc.AudioFrame(
                    data=chunk,
                    sample_rate=getattr(tpl, "sample_rate", schemas.FALLBACK_NATIVE_SR),
                    num_channels=ch,
                    samples_per_channel=spc,
                )
            except Exception:
                return None

    def stats(self) -> dict:
        avg = (self._total_latency_ms / self._frames_processed) if self._frames_processed else 0
        return {
            "provider": "quail",
            "enabled": self._enabled,
            "model_loaded": client.is_model_loaded(),
            "model_id": self._model_id,
            "native_sr": self._proc_sr,
            "block_frames": self._proc_num_frames,
            "blocks_processed": self._frames_processed,
            "avg_latency_ms": round(avg, 2),
        }


# Backwards-compat alias so existing imports/instantiations keep working.
DeepFilterDenoiser = QuailNoiseCanceller
QuailDenoiser = QuailNoiseCanceller
