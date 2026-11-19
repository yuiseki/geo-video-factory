#!/usr/bin/env python3
"""Generate a seamless 16-second license-clean ambient BGM WAV (BPM 90) avoiding voice frequencies."""

from __future__ import annotations
import math
import struct
import wave
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parents[1] / "assets" / "bgm.wav"
SAMPLE_RATE = 48000
DURATION = 16.0  # 8 bars at 120bpm or 6 bars at 90bpm -> seamless loop


def main() -> None:
    n_samples = int(SAMPLE_RATE * DURATION)
    # Warm low-mid chord progression (Cmaj9 -> Am9 -> Fmaj9 -> G6), 4 seconds each
    chords = [
        [130.81, 196.00, 246.94, 293.66],  # Cmaj9 (C3, G3, B3, D4)
        [110.00, 164.81, 220.00, 246.94],  # Am9 (A2, E3, A3, B3)
        [87.31,  174.61, 220.00, 261.63],  # Fmaj7 (F2, F3, A3, C4)
        [98.00,  146.83, 196.00, 246.94],  # G6 (G2, D3, G3, B3)
    ]
    # Gentle arpeggio notes per 0.5s step (8 steps per 4s chord)
    arp_freqs = [
        [261.63, 329.63, 392.00, 493.88, 392.00, 329.63, 293.66, 329.63],
        [220.00, 261.63, 329.63, 392.00, 329.63, 261.63, 246.94, 261.63],
        [174.61, 220.00, 261.63, 329.63, 261.63, 220.00, 261.63, 293.66],
        [196.00, 246.94, 293.66, 392.00, 293.66, 246.94, 220.00, 246.94],
    ]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    buf = bytearray()
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        chord_idx = int(t // 4.0) % 4
        local_t = t % 4.0
        # Smooth crossfade envelope within each 4s chord
        env_pad = min(1.0, local_t / 0.35) * min(1.0, (4.0 - local_t) / 0.35)
        pad = 0.0
        for f in chords[chord_idx]:
            pad += math.sin(2.0 * math.pi * f * t)
        pad = (pad / len(chords[chord_idx])) * 0.28 * (0.35 + 0.65 * env_pad)

        # Gentle plucked sine bell (low-mid only, soft attack/decay)
        step_idx = int(local_t / 0.5) % 8
        step_t = local_t % 0.5
        arp_f = arp_freqs[chord_idx][step_idx]
        env_arp = min(1.0, step_t / 0.025) * math.exp(-step_t * 4.5)
        arp = math.sin(2.0 * math.pi * arp_f * t) * 0.14 * env_arp

        # Global 20ms loop-boundary fade to prevent click
        loop_env = min(1.0, t / 0.02) * min(1.0, (DURATION - t) / 0.02)
        val = (pad + arp) * loop_env
        s = max(-32767, min(32767, int(val * 32767)))
        buf += struct.pack("<hh", s, s)

    with wave.open(str(OUT_PATH), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(buf))
    print(f"Generated seamless BGM: {OUT_PATH} ({DURATION}s)")


if __name__ == "__main__":
    main()
