"""
media_recorder.py
=================
Best-effort local WAV recorder for phone calls.

Collects timestamped mono PCM chunks (16-bit signed) and builds a mixed timeline
recording at call end. This allows us to persist call recordings for both
telephony providers even when provider-side recording webhooks are unavailable.
"""

from __future__ import annotations

import audioop
import os
import re
import time
import wave
import logging
from array import array
from typing import Optional

logger = logging.getLogger("telephony.media_recorder")


def _safe_name(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (raw or "").strip())
    return cleaned.strip("-._") or f"call-{int(time.time() * 1000)}"


def _resample_linear_pcm(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if not pcm or src_rate <= 0 or dst_rate <= 0 or src_rate == dst_rate:
        return pcm

    # Prefer C-backed resampling for better quality and lower CPU on telephony audio.
    try:
        converted, _ = audioop.ratecv(pcm, 2, 1, src_rate, dst_rate, None)
        if converted:
            return converted
    except Exception:
        pass

    src = array("h")
    src.frombytes(pcm)
    if not src:
        return b""

    src_len = len(src)
    dst_len = max(1, int(src_len * dst_rate / src_rate))
    out = array("h", [0] * dst_len)

    for i in range(dst_len):
        pos = i * (src_len - 1) / max(1, dst_len - 1)
        left = int(pos)
        right = min(left + 1, src_len - 1)
        frac = pos - left
        val = int(src[left] + frac * (src[right] - src[left]))
        out[i] = max(-32768, min(32767, val))
    return out.tobytes()


def _apply_gain_pcm(pcm: bytes, gain: float) -> bytes:
    if not pcm:
        return b""
    try:
        g = float(gain)
    except Exception:
        g = 1.0
    if g <= 0:
        return b""
    if abs(g - 1.0) < 1e-3:
        return pcm

    src = array("h")
    src.frombytes(pcm)
    if not src:
        return b""
    out = array("h", [0] * len(src))
    for i, val in enumerate(src):
        scaled = int(val * g)
        out[i] = max(-32768, min(32767, scaled))
    return out.tobytes()


class CallMediaRecorder:
    """Collect timestamped chunks and render one mono WAV file."""

    def __init__(self, sample_rate: int = 8000):
        self.sample_rate = int(sample_rate or 8000)
        self._segments: list[tuple[float, bytes, str]] = []
        self._source_sample_counts: dict[str, int] = {}
        self._source_next_ts: dict[str, float] = {}

    def add_pcm(
        self,
        pcm: bytes,
        sample_rate: Optional[int] = None,
        ts: Optional[float] = None,
        source: str = "unknown",
        gain: float = 1.0,
    ) -> None:
        if not pcm:
            return
        rate = int(sample_rate or self.sample_rate)
        data = pcm if rate == self.sample_rate else _resample_linear_pcm(pcm, rate, self.sample_rate)
        data = _apply_gain_pcm(data, gain)
        if not data:
            return
        src = (source or "unknown").strip().lower() or "unknown"
        if ts is None:
            now_ts = float(time.time())
            duration = (len(data) / 2.0) / float(self.sample_rate)
            start_ts = max(now_ts, self._source_next_ts.get(src, now_ts))
            self._source_next_ts[src] = start_ts + max(0.0, duration)
        else:
            start_ts = float(ts)
            duration = (len(data) / 2.0) / float(self.sample_rate)
            self._source_next_ts[src] = max(self._source_next_ts.get(src, start_ts), start_ts + max(0.0, duration))

        self._segments.append((start_ts, bytes(data), src))
        self._source_sample_counts[src] = self._source_sample_counts.get(src, 0) + (len(data) // 2)

    def has_audio(self) -> bool:
        return bool(self._segments)

    def save_wav(self, output_dir: str, file_stem: str) -> Optional[str]:
        if not self._segments:
            return None

        ordered = sorted(self._segments, key=lambda x: x[0])
        start_ts = ordered[0][0]

        prepared: list[tuple[int, array]] = []
        total_samples = 0
        for ts, pcm, _source in ordered:
            samples = array("h")
            samples.frombytes(pcm)
            if not samples:
                continue
            start_sample = max(0, int((ts - start_ts) * self.sample_rate))
            prepared.append((start_sample, samples))
            total_samples = max(total_samples, start_sample + len(samples))

        if total_samples <= 0:
            return None

        # Use signed int accumulator to avoid clipping during overlay.
        mix = array("i", [0] * total_samples)
        for start_sample, samples in prepared:
            for idx, val in enumerate(samples):
                mix[start_sample + idx] += int(val)

        peak = 0
        for val in mix:
            abs_val = abs(val)
            if abs_val > peak:
                peak = abs_val
        if peak <= 0:
            return None

        target_peak = float(os.getenv("RECORDING_TARGET_PEAK", "0.85"))
        target_peak = max(0.1, min(0.98, target_peak))
        max_gain = float(os.getenv("RECORDING_MAX_GAIN", "6.0"))
        max_gain = max(1.0, min(12.0, max_gain))
        target_amp = max(1000, int(32767 * target_peak))
        scale = target_amp / float(peak)
        if scale > max_gain:
            scale = max_gain
        min_scale = float(os.getenv("RECORDING_MIN_SCALE", "0.35"))
        min_scale = max(0.05, min(1.0, min_scale))
        if scale < min_scale:
            scale = min_scale
        if scale <= 0:
            scale = 1.0

        out = array("h", [0] * total_samples)
        for idx, val in enumerate(mix):
            scaled = int(val * scale)
            out[idx] = max(-32768, min(32767, scaled))

        os.makedirs(output_dir, exist_ok=True)
        filename = f"{_safe_name(file_stem)}.wav"
        path = os.path.join(output_dir, filename)

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(out.tobytes())

        sources = ", ".join(
            f"{name}:{count}"
            for name, count in sorted(self._source_sample_counts.items(), key=lambda x: x[0])
        ) or "none"
        logger.info(
            "Saved call recording: %s (%d samples, peak=%d, scale=%.2f, sources=%s)",
            path,
            total_samples,
            peak,
            scale,
            sources,
        )
        return path
