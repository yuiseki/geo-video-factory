"""A calm ambient piece synthesized from sines and noise only: nothing is sampled, so there is no licence to clear.

D major, four chords of 8 s (60 BPM, two bars each): soft pads, a sub bass, sparse bell notes on the pentatonic
scale with an echo, a breath of filtered noise, and one long reverb. With a night start the chords turn to
B minor from the nearest chord boundary on, the bells drop an octave and thin out. The piece fades in over 3 s and
out over 7 s. 48 kHz, 16 bit, stereo; the loudness is left to the mastering step (ffmpeg loudnorm).

    python ambient_bgm.py <out.wav> <seconds> [--night-from=<s>] [--seed=7]

Everything random comes from one seeded generator, drawn in a fixed order (pads and bells chord by chord, then
the noise bed, then the reverb), so the same arguments give the same file. The order is part of the output: a
change that draws one number more or less changes every sample after it.
"""
from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np
from scipy import signal

SR = 48000
CHORD = 8.0
A4 = 440.0
FADE_IN, FADE_OUT = 3.0, 7.0
PEAK_DB = -3.0

DAY = [("D2", ["A3", "D4", "F#4", "E5"]), ("B1", ["A3", "D4", "F#4", "C#5"]),
       ("G2", ["B3", "D4", "F#4", "A4"]), ("A1", ["B3", "D4", "E4", "A4"])]
NIGHT = [("B1", ["F#3", "B3", "D4", "A4"]), ("G1", ["G3", "B3", "D4", "F#4"]),
         ("E2", ["G3", "B3", "E4", "F#4"]), ("F#1", ["F#3", "A3", "C#4", "E4"])]
BELLS_DAY = ["D5", "E5", "F#5", "A5", "B5", "D6"]
BELLS_NIGHT = ["B4", "D5", "E5", "F#5", "A5"]


def hz(note: str) -> float:
    """'D4', 'F#4', 'Bb3' -> Hz."""
    names = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)
    n = names[note[0]] + note.count("#") - note.count("b")
    return A4 * 2 ** ((n - 9) / 12 + int(note[-1]) - 4)


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    e[:a] = 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
    e[-r:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(r) / r)
    return e


def pad(freq: float, seconds: float, rng: np.random.Generator) -> np.ndarray:
    """Two slightly detuned voices of a few soft harmonics, one a little to the left and one to the right."""
    t = np.arange(int(seconds * SR)) / SR
    out = np.zeros((len(t), 2))
    for side, cents in ((0, -5.0), (1, 5.0)):
        f = freq * 2 ** (cents / 1200)
        v = sum(np.sin(2 * np.pi * f * k * t + rng.uniform(0, 6.28)) / k ** 2.2 for k in range(1, 6))
        v *= 1 + 0.08 * np.sin(2 * np.pi * rng.uniform(0.08, 0.2) * t + rng.uniform(0, 6.28))
        out[:, side] += 0.7 * v
        out[:, 1 - side] += 0.3 * v
    return out * envelope(len(t), 3.0, 4.0)[:, None]


def bell(freq: float, seconds: float = 5.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    v = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2.005 * t) * np.exp(-t / 0.5)
    v += 0.12 * np.sin(2 * np.pi * freq * 3.01 * t) * np.exp(-t / 0.25)
    return v * np.exp(-t / 1.1) * np.minimum(t / 0.008, 1)


def add(mix: np.ndarray, start: float, sound: np.ndarray) -> None:
    """Mixes the sound into the piece at start seconds; what falls before or after the piece is cut."""
    i = int(start * SR)
    if i < 0:  # a sound that begins before the piece does: its head is cut
        sound, i = sound[-i:], 0
    n = min(len(sound), len(mix) - i)
    if n > 0:
        mix[i:i + n] += sound[:n]


def night_boundary(night_from: float) -> float:
    """The chord boundary where the night chords begin. A time exactly halfway between two boundaries goes to
    the even-numbered chord (Python's round), so 12 s gives 16 s but 20 s gives 16 s as well."""
    return round(night_from / CHORD) * CHORD


def score(seconds: float, rng: np.random.Generator, night_from: float | None = None):
    """The notes before any filtering: (pads, bass, bells), each (samples, 2)."""
    n = int(seconds * SR)
    pads, bass, bells = np.zeros((n, 2)), np.zeros((n, 2)), np.zeros((n, 2))
    for c in range(int(np.ceil(seconds / CHORD))):
        t0 = c * CHORD
        night = night_from is not None and t0 >= night_boundary(night_from)
        root, notes = (NIGHT if night else DAY)[c % 4]
        for note in notes:
            add(pads, t0 - 1.5, 0.16 * pad(hz(note), CHORD + 4.5, rng))  # overlaps its neighbours: no gap between chords
        t = np.arange(int((CHORD + 2) * SR)) / SR
        sub = np.sin(2 * np.pi * hz(root) * t) + 0.3 * np.sin(2 * np.pi * 2 * hz(root) * t)
        add(bass, t0 - 0.5, 0.22 * (sub * envelope(len(t), 1.5, 2.5))[:, None] * np.ones(2))
        if t0 < 8:  # the first chord stands alone
            continue
        scale = BELLS_NIGHT if night else BELLS_DAY
        last = None
        for step in range(16):  # half-second grid
            if rng.random() < (0.10 if night else 0.17):
                note = rng.choice([s for s in scale if s != last])
                last = note
                pan = rng.uniform(0.25, 0.75)
                b = 0.10 * rng.uniform(0.6, 1.0) * bell(hz(note))
                add(bells, t0 + step * 0.5, np.stack([b * (1 - pan), b * pan], 1))
    return pads, bass, bells


def render(seconds: float, night_from: float | None = None, seed: int = 7) -> np.ndarray:
    """The finished piece as float samples (samples, 2), its peak at PEAK_DB.

    The noise bed and the reverb are drawn after the notes from the same generator, and a night section draws a
    different number of bell notes. So night_from changes the noise and the reverb tails of the whole piece, not
    only the chords after the boundary.
    """
    if seconds < FADE_OUT:
        raise ValueError(f"the piece must last at least {FADE_OUT:g} s, the length of its fade-out: got {seconds:g}")
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    pads, bass, bells = score(seconds, rng, night_from)
    # the echo of the bells: three repeats, alternating sides
    echo = bells.copy()
    for k, gain in enumerate((0.45, 0.25, 0.12), 1):
        d = int(0.75 * k * SR)
        echo[d:, k % 2] += gain * bells[:-d, (k + 1) % 2]
    pads = signal.sosfilt(signal.butter(2, 1700, "low", fs=SR, output="sos"), pads, axis=0)
    air = signal.sosfilt(signal.butter(2, [250, 2200], "band", fs=SR, output="sos"), rng.normal(0, 1, (n, 2)), axis=0)
    t = np.arange(n) / SR
    air *= (0.006 * (1 + 0.5 * np.sin(2 * np.pi * t / 23)))[:, None]
    dry = pads + bass + echo + air
    # one long reverb: noise that dies away, a different one for each ear
    tr = np.arange(int(4.5 * SR)) / SR
    wet = np.zeros_like(dry)
    send = pads + 1.4 * echo + air
    for ch in range(2):
        ir = rng.normal(0, 1, len(tr)) * np.exp(-tr / 1.4) * np.minimum(tr / 0.02, 1)
        ir = signal.sosfilt(signal.butter(2, 4500, "low", fs=SR, output="sos"), ir)
        ir /= np.sqrt((ir ** 2).sum())
        wet[:, ch] = signal.fftconvolve(send[:, ch], ir)[:n]
    mix = dry + 0.55 * wet
    fade = np.ones(n)
    a, r = int(FADE_IN * SR), int(FADE_OUT * SR)
    fade[:a] = np.linspace(0, 1, a) ** 2
    fade[-r:] = (0.5 + 0.5 * np.cos(np.pi * np.arange(r) / r))
    mix *= fade[:, None]
    mix *= 10 ** (PEAK_DB / 20) / np.abs(mix).max()
    return mix


def write_wav(path: Path | str, mix: np.ndarray) -> None:
    """Float samples in [-1, 1] as a 16 bit stereo WAV."""
    with wave.open(str(path), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes((mix * 32767).astype("<i2").tobytes())


def main(argv: list[str] | None = None) -> int:
    # Abbreviations are off so that a mistyped option stops the run instead of quietly becoming another one.
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    parser.add_argument("out", help="the WAV file to write")
    parser.add_argument("seconds", type=float)
    parser.add_argument("--night-from", type=float, default=None, metavar="S",
                        help="turn to the night chords at the chord boundary nearest to this second")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    mix = render(args.seconds, night_from=args.night_from, seed=args.seed)
    write_wav(args.out, mix)
    print(f"{args.out}: {args.seconds:.1f} s, peak {20 * np.log10(np.abs(mix).max()):.1f} dBFS, "
          f"rms {20 * np.log10(np.sqrt((mix ** 2).mean())):.1f} dBFS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
