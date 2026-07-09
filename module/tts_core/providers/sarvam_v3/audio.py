"""
Audio normalization for Sarvam v3 TTS.

Sarvam v3 may return WAV-wrapped audio (REST `/text-to-speech`, and WS chunks
when output_audio_codec isn't explicitly set to a raw format). The worker
publishes whatever bytes a provider yields straight to LiveKit as 16-bit PCM,
so WAV containers must be unwrapped before they reach the worker.

IMPORTANT — do not "guess" bit depth on already-PCM data:
A naive version of this helper used to fall back to trying both 16-bit and
8-bit reinterpretation whenever a non-WAV payload had an odd number of bytes.
That guess is wrong for streamed WebSocket chunks: a 16-bit-PCM stream split
mid-sample produces an odd-length chunk that is NOT 8-bit audio — reinterpreting
it as 8-bit and upsampling corrupts/garbles that chunk. The fix here never
reinterprets bit-depth on non-WAV data; it only unwraps real WAV containers,
and otherwise passes raw bytes through untouched (sample-boundary alignment
across chunks is handled by the caller, same as it already is for Cartesia).
"""
from __future__ import annotations

import audioop
import io
import logging
import wave

log = logging.getLogger("tts_core.sarvam_v3")


def coerce_to_pcm(payload: bytes, sample_rate: int) -> bytes:
    """Return raw 16-bit mono PCM at `sample_rate`.

    - WAV-wrapped payloads (start with b"RIFF") are unwrapped, resampled, and
      downmixed to mono if needed.
    - Anything else is assumed to already be raw PCM (e.g. a WebSocket binary
      frame with output_audio_codec="linear16") and is returned unchanged —
      never bit-depth-guessed.
    """
    if not payload:
        return b""

    if not payload.startswith(b"RIFF"):
        return payload

    try:
        with wave.open(io.BytesIO(payload), "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            frame_rate = wf.getframerate()
            pcm = wf.readframes(wf.getnframes())
    except wave.Error as exc:
        log.warning("Sarvam v3: payload looked like WAV but failed to parse (%s) — passing through raw", exc)
        return payload

    if not pcm:
        return b""

    try:
        if sampwidth != 2:
            pcm = audioop.lin2lin(pcm, sampwidth, 2)
        if channels == 2:
            pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
        elif channels not in (1, 2):
            log.warning("Sarvam v3: unsupported channel count %d — passing through raw", channels)
            return payload
        if frame_rate != sample_rate:
            pcm, _ = audioop.ratecv(pcm, 2, 1, frame_rate, sample_rate, None)
        return pcm
    except audioop.error as exc:
        log.warning("Sarvam v3: PCM conversion failed (%s) — passing through raw", exc)
        return payload
