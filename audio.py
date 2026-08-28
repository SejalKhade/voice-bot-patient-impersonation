"""
Audio primitives for the Twilio media bridge.

Twilio Media Streams speak exactly one dialect: 8 kHz mono G.711 mu-law,
base64-encoded, in 20 ms frames of 160 bytes. Everything in this module
exists to get audio into or out of that shape.

Implemented with numpy rather than `audioop` on purpose. `audioop` was
removed from the standard library in Python 3.13, and pulling in ffmpeg
just to resample a phone call is a heavy dependency for a test harness.
"""

from __future__ import annotations

import base64
import math
from typing import Iterator

import numpy as np

# Twilio frame geometry.
SAMPLE_RATE = 8000
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * FRAME_MS // 1000  # 160 samples == 160 mu-law bytes

# G.711 constants, following the ITU reference implementation.
#
# The encoder works in a 14-bit domain: the 16-bit input is shifted down by
# two before anything else happens. The decoder returns 16-bit directly.
# Keeping to the reference's domains rather than rescaling them is the
# difference between a clean line and audio four times too loud, which
# clips into distortion and wrecks the far end's own transcription.
_MU_BIAS = 0x84          # 132, decoder-side bias in the 16-bit domain
_MU_BIAS_14 = _MU_BIAS >> 2   # 33, encoder-side bias in the 14-bit domain
_MU_CLIP_14 = 8159       # maximum magnitude in the 14-bit domain

# seg_uend from the reference, in the 14-bit domain: 63, 127, ... 8191.
_SEG_THRESHOLDS = [1 << (b + 5) for b in range(1, 8)]  # 64, 128, ... 4096


def _segment(values: np.ndarray) -> np.ndarray:
    """Exponent segment for each biased 14-bit magnitude."""
    seg = np.zeros(values.shape, dtype=np.int32)
    for index, threshold in enumerate(_SEG_THRESHOLDS, start=1):
        seg = np.where(values >= threshold, index, seg)
    return seg


def pcm16_to_mulaw(pcm: np.ndarray) -> bytes:
    """Encode signed 16-bit PCM to G.711 mu-law bytes."""
    samples = np.asarray(pcm, dtype=np.int32) >> 2  # into the 14-bit domain

    # The reference folds the sign into an XOR mask rather than an OR: 0xFF
    # for positive samples, 0x7F for negative. Complementing only the low
    # seven bits on the negative branch is what leaves the decoder's sign
    # bit in the right state.
    mask = np.where(samples < 0, 0x7F, 0xFF).astype(np.int32)
    magnitude = np.minimum(np.abs(samples), _MU_CLIP_14) + _MU_BIAS_14

    exponent = _segment(magnitude)
    mantissa = (magnitude >> (exponent + 1)) & 0x0F
    encoded = ((exponent << 4) | mantissa) ^ mask
    return (encoded & 0xFF).astype(np.uint8).tobytes()


def mulaw_to_pcm16(payload: bytes) -> np.ndarray:
    """Decode G.711 mu-law bytes to signed 16-bit PCM."""
    encoded = np.frombuffer(payload, dtype=np.uint8).astype(np.int32)
    encoded = ~encoded & 0xFF

    sign = encoded & 0x80
    exponent = (encoded >> 4) & 0x07
    mantissa = encoded & 0x0F

    magnitude = ((mantissa << 3) + _MU_BIAS) << exponent
    magnitude -= _MU_BIAS
    pcm = np.where(sign != 0, -magnitude, magnitude)
    return np.clip(pcm, -32768, 32767).astype(np.int16)


def downsample_pcm16(pcm: np.ndarray, source_rate: int, target_rate: int = SAMPLE_RATE) -> np.ndarray:
    """
    Rate-convert PCM with a windowed-sinc low-pass first.

    Naive decimation folds everything above the new Nyquist back into the
    band as aliasing, which on a phone line sounds like a metallic buzz and
    measurably degrades the far-end agent's own speech recognition. The
    filter is cheap insurance.
    """
    if source_rate == target_rate:
        return np.asarray(pcm, dtype=np.int16)

    ratio = source_rate / target_rate
    cutoff = 0.5 / ratio
    taps = 64
    n = np.arange(taps) - (taps - 1) / 2
    kernel = np.sinc(2 * cutoff * n) * np.hamming(taps)
    kernel /= kernel.sum()

    filtered = np.convolve(np.asarray(pcm, dtype=np.float64), kernel, mode="same")
    positions = np.arange(0, len(filtered), ratio)
    resampled = np.interp(positions, np.arange(len(filtered)), filtered)
    return np.clip(resampled, -32768, 32767).astype(np.int16)


def pcm16_bytes_to_mulaw(raw: bytes, source_rate: int) -> bytes:
    """Convenience path for TTS providers that only emit linear PCM."""
    pcm = np.frombuffer(raw, dtype=np.int16)
    return pcm16_to_mulaw(downsample_pcm16(pcm, source_rate))


def frames(mulaw: bytes, frame_bytes: int = FRAME_BYTES) -> Iterator[bytes]:
    """Split a mu-law buffer into Twilio-sized frames, zero-padding the tail."""
    for start in range(0, len(mulaw), frame_bytes):
        chunk = mulaw[start:start + frame_bytes]
        if len(chunk) < frame_bytes:
            chunk = chunk + b"\xff" * (frame_bytes - len(chunk))  # mu-law silence
        yield chunk


def encode_frame(frame: bytes) -> str:
    return base64.b64encode(frame).decode("ascii")


def decode_payload(payload: str) -> bytes:
    return base64.b64decode(payload)


def duration_seconds(mulaw: bytes) -> float:
    return len(mulaw) / SAMPLE_RATE


def rms_dbfs(mulaw: bytes) -> float:
    """
    Loudness of a mu-law buffer in dBFS.

    Used by the metrics layer to distinguish real silence from a dead or
    one-way audio path, which are different bugs with different owners.
    """
    if not mulaw:
        return -math.inf
    pcm = mulaw_to_pcm16(mulaw).astype(np.float64)
    rms = float(np.sqrt(np.mean(pcm ** 2)))
    if rms <= 0:
        return -math.inf
    return 20 * math.log10(rms / 32768.0)
