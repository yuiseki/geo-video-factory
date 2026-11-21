#!/usr/bin/env python3
"""Generate a license-clean Mallsoft / Slushwave style Vaporwave BGM loop locally."""
from __future__ import annotations

import argparse
from pathlib import Path
import wave
import numpy as np


SAMPLE_RATE = 48000


def midi_to_hz(midi: float, a4: float = 432.0) -> float:
    # Slightly detuned A4=432Hz for a nostalgic, slowed-down tape feel
    return a4 * (2.0 ** ((midi - 69.0) / 12.0))


def lowpass_1pole(signal: np.ndarray, cutoff_hz: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    rc = 1.0 / (2.0 * np.pi * cutoff_hz)
    dt = 1.0 / sr
    alpha = dt / (rc + dt)
    out = np.empty_like(signal)
    y = 0.0
    for i in range(len(signal)):
        y += alpha * (signal[i] - y)
        out[i] = y
    return out


def schroeder_reverb(stereo: np.ndarray, sr: int = SAMPLE_RATE, wet: float = 0.52) -> np.ndarray:
    """Simple lush stereo feedback-delay network / multi-tap reverb for Slushwave feel."""
    n = stereo.shape[0]
    out = np.zeros_like(stereo)
    # Prime-like delay times in ms for left and right channels
    taps_l = [43, 67, 109, 163, 241, 359]
    taps_r = [47, 73, 113, 173, 257, 379]
    decays = [0.68, 0.62, 0.56, 0.48, 0.40, 0.32]

    for ch, taps in enumerate([taps_l, taps_r]):
        buf = stereo[:, ch].copy()
        acc = np.zeros(n, dtype=np.float64)
        for ms, g in zip(taps, decays):
            d = int(sr * ms / 1000.0)
            delayed = np.zeros(n, dtype=np.float64)
            delayed[d:] = buf[:-d]
            # Wrap tail to beginning for seamless loop
            delayed[:d] += buf[-d:] * 0.5
            acc += delayed * g
        # Soften high frequencies in reverb tail
        acc = lowpass_1pole(acc, 2400.0, sr)
        out[:, ch] = stereo[:, ch] * (1.0 - wet) + acc * wet
    return out


def synth_pad_chord(
    freqs: list[float],
    duration_sec: float,
    sr: int = SAMPLE_RATE,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(sr * duration_sec)
    t = np.arange(n, dtype=np.float64) / sr
    # Slow tape wow/flutter pitch modulation
    wow = 1.0 + 0.0028 * np.sin(2.0 * np.pi * 0.35 * t + 0.4) + 0.0012 * np.sin(2.0 * np.pi * 0.85 * t)

    left = np.zeros(n, dtype=np.float64)
    right = np.zeros(n, dtype=np.float64)

    for idx, f in enumerate(freqs):
        # Detuned dual voices panned slightly L/R
        detune_l = 0.9965 - 0.001 * (idx % 2)
        detune_r = 1.0035 + 0.001 * (idx % 2)
        p0_l = rng.uniform(0, 2 * np.pi)
        p0_r = rng.uniform(0, 2 * np.pi)

        phase_l = 2.0 * np.pi * np.cumsum(f * detune_l * wow) / sr + p0_l
        phase_r = 2.0 * np.pi * np.cumsum(f * detune_r * wow) / sr + p0_r

        # Warm triangle + soft 2nd/3rd harmonic
        v_l = 0.70 * np.sin(phase_l) + 0.22 * np.sin(2.0 * phase_l) + 0.08 * np.sin(3.0 * phase_l)
        v_r = 0.70 * np.sin(phase_r) + 0.22 * np.sin(2.0 * phase_r) + 0.08 * np.sin(3.0 * phase_r)

        pan = 0.35 + 0.3 * (idx / max(1, len(freqs) - 1))
        left += v_l * (1.0 - pan * 0.4)
        right += v_r * (0.6 + pan * 0.4)

    # Smooth ADSR envelope so chord transitions swell softly
    attack = int(sr * min(0.9, duration_sec * 0.22))
    release = int(sr * min(1.0, duration_sec * 0.25))
    env = np.ones(n, dtype=np.float64)
    if attack > 0:
        env[:attack] = 0.5 * (1.0 - np.cos(np.pi * np.arange(attack) / attack))
    if release > 0:
        env[-release:] = 0.5 * (1.0 + np.cos(np.pi * np.arange(release) / release))

    stereo = np.stack([left, right], axis=1) * env[:, None] / max(1.0, len(freqs) * 0.7)
    return stereo


def synth_bell_note(freq: float, duration_sec: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Soft retro electric-piano / chime accent."""
    n = int(sr * duration_sec)
    t = np.arange(n, dtype=np.float64) / sr
    attack = np.minimum(1.0, t / 0.025)
    decay = np.exp(-t * 1.45)
    tone = (
        0.75 * np.sin(2.0 * np.pi * freq * t)
        + 0.25 * np.sin(2.0 * np.pi * freq * 2.0 * t) * np.exp(-t * 2.8)
    )
    val = tone * attack * decay * 0.35
    return np.stack([val * 0.95, val * 1.05], axis=1)


def build_vaporwave_bgm(duration_sec: float = 24.0) -> np.ndarray:
    # 4-chord dreamy city-pop / Mallsoft progression (6s per chord = 24s seamless loop)
    # Fmaj9 -> Em7 -> Dm9 -> Cmaj9 (shifted down 1 semitone for extra mellow night mood)
    chords_midi = [
        [40, 52, 56, 59, 63, 66],  # Emaj9
        [39, 51, 54, 58, 61],      # D#m7
        [37, 49, 52, 56, 59, 63],  # C#m9
        [35, 47, 51, 54, 58, 61],  # Bmaj9
    ]
    chord_dur = duration_sec / len(chords_midi)
    total_samples = int(SAMPLE_RATE * duration_sec)
    mix = np.zeros((total_samples, 2), dtype=np.float64)

    melody_notes = [
        (0.5, 75, 3.0),
        (3.5, 73, 2.5),
        (6.5, 70, 3.2),
        (10.0, 68, 2.5),
        (12.5, 71, 3.0),
        (15.5, 68, 2.5),
        (18.5, 66, 3.5),
        (21.5, 63, 2.5),
    ]

    for i, midi_list in enumerate(chords_midi):
        start = int(i * chord_dur * SAMPLE_RATE)
        freqs = [midi_to_hz(m) for m in midi_list]
        pad = synth_pad_chord(freqs, chord_dur + 0.6, seed=10 + i)
        end = min(total_samples, start + pad.shape[0])
        mix[start:end] += pad[: end - start]
        # Wrap tail for seamless loop
        overflow = start + pad.shape[0] - total_samples
        if overflow > 0:
            mix[:overflow] += pad[end - start :]

    for onset, midi, dur in melody_notes:
        start = int(onset * SAMPLE_RATE)
        note = synth_bell_note(midi_to_hz(midi), dur)
        end = min(total_samples, start + note.shape[0])
        mix[start:end] += note[: end - start]

    # Subtle fluorescent-light 60Hz/120Hz hum + soft analog tape hiss
    rng = np.random.default_rng(42)
    t = np.arange(total_samples, dtype=np.float64) / SAMPLE_RATE
    hum = 0.008 * np.sin(2.0 * np.pi * 60.0 * t) + 0.004 * np.sin(2.0 * np.pi * 120.0 * t)
    hiss = lowpass_1pole(rng.normal(0.0, 0.006, total_samples), 1800.0)
    mix[:, 0] += hum + hiss
    mix[:, 1] += hum + hiss * 0.9

    # Apply lush Slushwave/Mallsoft reverb and gentle lowpass
    mix = schroeder_reverb(mix, SAMPLE_RATE, wet=0.58)
    mix[:, 0] = lowpass_1pole(mix[:, 0], 2800.0)
    mix[:, 1] = lowpass_1pole(mix[:, 1], 2800.0)

    # Normalize safely before loudnorm
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix * (0.82 / peak)
    return mix


def write_wav(path: Path, stereo: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(stereo * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=24.0)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets/bgm/vaporwave_mallsoft.wav",
    )
    args = parser.parse_args()
    audio = build_vaporwave_bgm(args.duration)
    write_wav(args.out, audio)
    print(f"generated Vaporwave BGM ({args.duration:.1f}s): {args.out}")


if __name__ == "__main__":
    main()
