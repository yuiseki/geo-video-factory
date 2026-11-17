#!/usr/bin/env python3
"""Generate VOICEVOX narration, dynamic 176s BGM, subtle SFX, ducking, and -14 LUFS mix."""
from __future__ import annotations

import json
import math
import subprocess
import urllib.parse
import urllib.request
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent
AUDIO_DIR = PROJECT / "audio" / "generated"
VOICEVOX_URL = "http://127.0.0.1:50021"
SR = 48000
TOTAL_SEC = 176.0

# (clip_id, offset_in_total_sec, display_text, speech_text)
NARRATION_LINES = [
    ("S02", 10.2, "テクスチャのないPLATEAUの建物にも、地理院シームレス空中写真と推定モデルで外観を与えられます。",
     "テクスチャのないプラトーの建物にも、地理院シームレス空中写真と推定モデルで外観を与えられます。"),
    ("B03", 40.0, "一方、PLATEAUがまだ整備されていない地域もあります。",
     "一方、プラトーがまだ整備されていない地域もあります。"),
    ("S04", 48.0, "地理院ベクトルタイルと隣の福生市のデータを組み合わせ、高さと外観を推定します。",
     "地理院ベクトルタイルと、隣の福生市のデータを組み合わせ、高さと外観を推定します。"),
    ("S05", 75.2, "同じ仕組みは、大阪の湾岸から市街地までそのまま適用できます。",
     "同じ仕組みは、大阪の湾岸から市街地まで、そのまま適用できます。"),
    ("S07", 115.2, "衛星データの色を転写すれば、同じ地形に四季をまとわせられます。",
     "衛星データの色を転写すれば、同じ地形に四季をまとわせられます。"),
    ("S08", 126.2, "カメラの動きも建物の演出も、AIがJSONに書き、ソフトウェアが描画します。",
     "カメラの動きも建物の演出も、エーアイがジェイソンに書き、ソフトウェアが描画します。"),
    ("S10", 170.0, "この映像を作るソフトウェアは、オープンソースで無料公開しています。",
     "この映像を作るソフトウェアは、オープンソースで無料公開しています。"),
]


def synth_voicevox(text: str, out_wav: Path, speaker: int = 2, speed: float = 1.18) -> float:
    if out_wav.exists():
        with wave.open(str(out_wav), "rb") as w:
            return w.getnframes() / w.getframerate()
    q_url = f"{VOICEVOX_URL}/audio_query?text={urllib.parse.quote(text)}&speaker={speaker}"
    req = urllib.request.Request(q_url, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        query = json.loads(resp.read().decode("utf-8"))
    query["speedScale"] = speed
    query["volumeScale"] = 1.0
    s_url = f"{VOICEVOX_URL}/synthesis?speaker={speaker}"
    req2 = urllib.request.Request(
        s_url,
        data=json.dumps(query).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req2, timeout=60) as resp:
        out_wav.write_bytes(resp.read())
    with wave.open(str(out_wav), "rb") as w:
        return w.getnframes() / w.getframerate()


def write_stereo_wav(path: Path, left: np.ndarray, right: np.ndarray) -> None:
    peak = max(float(np.max(np.abs(left))), float(np.max(np.abs(right))), 1e-6)
    if peak > 0.95:
        scale = 0.95 / peak
        left = left * scale
        right = right * scale
    interleaved = np.empty(left.size * 2, dtype=np.int16)
    interleaved[0::2] = np.clip(left * 32767.0, -32767, 32767).astype(np.int16)
    interleaved[1::2] = np.clip(right * 32767.0, -32767, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(interleaved.tobytes())


def read_wav_mono_48k(path: Path) -> np.ndarray:
    tmp = path.with_suffix(".48k.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-ar", str(SR), "-ac", "1", str(tmp)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
    )
    with wave.open(str(tmp), "rb") as w:
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    tmp.unlink(missing_ok=True)
    return raw


def generate_bgm(out_wav: Path) -> None:
    if out_wav.exists():
        return
    n = int(TOTAL_SEC * SR)
    t = np.linspace(0, TOTAL_SEC, n, endpoint=False, dtype=np.float64)
    left = np.zeros(n, dtype=np.float64)
    right = np.zeros(n, dtype=np.float64)

    # Chord progression in C minor / Eb major (16s cycle -> 4 chords x 4s)
    chords = [
        (130.81, 155.56, 196.00, 233.08),  # Cm7
        (103.83, 130.81, 155.56, 196.00),  # Abmaj7
        (116.54, 146.83, 174.61, 233.08),  # Bb6
        (98.00, 146.83, 174.61, 196.00),   # Gm7
    ]

    # Soft pad layer across the whole 176s
    for idx in range(int(TOTAL_SEC // 4)):
        s0 = idx * 4 * SR
        s1 = min((idx + 1) * 4 * SR, n)
        seg_t = t[s0:s1] - idx * 4.0
        dur = (s1 - s0) / SR
        env = np.sin(np.pi * np.clip(seg_t / dur, 0, 1)) ** 0.45
        notes = chords[idx % len(chords)]
        # Scale intensity by narrative arc
        sec = idx * 4.0
        if sec < 9:
            gain = 0.28
        elif sec < 92:
            gain = 0.22
        elif sec < 125:
            gain = 0.25  # calm mountain pad
        elif sec < 136:
            gain = 0.20
        elif sec < 169:
            gain = 0.34  # Hakodate climax
        else:
            gain = 0.18  # ending resolve
        pad_l = np.zeros_like(seg_t)
        pad_r = np.zeros_like(seg_t)
        for j, freq in enumerate(notes):
            detune = 1.0 + (j - 1.5) * 0.0018
            w1 = np.sin(2 * np.pi * freq * detune * seg_t)
            w2 = 0.35 * np.sin(2 * np.pi * freq * 2.0 * seg_t)
            pan = 0.35 + 0.3 * (j / max(1, len(notes) - 1))
            pad_l += (w1 + w2) * (1.0 - pan)
            pad_r += (w1 + w2) * pan
        left[s0:s1] += pad_l * env * gain * 0.22
        right[s0:s1] += pad_r * env * gain * 0.22

    # Gentle rhythmic pulse (only in urban/AI/climax sections, calm in Fuji/Omuro and Ending)
    beat_sec = 0.5  # 120 BPM
    for b in range(int(TOTAL_SEC / beat_sec)):
        sec = b * beat_sec
        if 92.0 <= sec < 125.0 or sec >= 169.0:
            continue  # calm during mountains & ending
        s0 = int(sec * SR)
        plen = int(0.18 * SR)
        s1 = min(s0 + plen, n)
        pt = np.arange(s1 - s0) / SR
        chord = chords[int(sec // 4) % len(chords)]
        note = chord[b % len(chord)] * 2.0
        env = np.exp(-pt * 18.0) * (1.0 - np.exp(-pt * 220.0))
        amp = 0.14 if sec >= 136.0 else 0.09
        if sec < 9.0:
            amp = 0.12
        tone = np.sin(2 * np.pi * note * pt) * env * amp
        pan = 0.45 if b % 2 == 0 else 0.55
        left[s0:s1] += tone * (1.0 - pan)
        right[s0:s1] += tone * pan

        # Sub pulse on downbeats
        if b % 2 == 0:
            sub_len = min(int(0.28 * SR), n - s0)
            st = np.arange(sub_len) / SR
            sub_env = np.exp(-st * 11.0)
            sub_f = chord[0] * 0.5
            sub = np.sin(2 * np.pi * sub_f * st) * sub_env * (0.18 if sec >= 136.0 else 0.11)
            left[s0:s0 + sub_len] += sub
            right[s0:s0 + sub_len] += sub

    # Smooth fade-in (0.3s) and ending fade-out (last 3.0s)
    fade_in = int(0.3 * SR)
    left[:fade_in] *= np.linspace(0, 1, fade_in)
    right[:fade_in] *= np.linspace(0, 1, fade_in)
    fade_out = int(3.0 * SR)
    left[-fade_out:] *= np.linspace(1, 0, fade_out)
    right[-fade_out:] *= np.linspace(1, 0, fade_out)

    write_stereo_wav(out_wav, left, right)


def add_sfx(buf_l: np.ndarray, buf_r: np.ndarray, sec: float, kind: str) -> None:
    s0 = int(sec * SR)
    if s0 >= buf_l.size:
        return
    if kind == "impact":
        dur = 1.2
        length = min(int(dur * SR), buf_l.size - s0)
        t = np.arange(length) / SR
        freq = 110.0 * np.exp(-t * 4.5) + 38.0
        phase = 2 * np.pi * np.cumsum(freq) / SR
        env = np.exp(-t * 3.8) * (1.0 - np.exp(-t * 150.0))
        sig = np.sin(phase) * env * 0.42
        buf_l[s0:s0 + length] += sig
        buf_r[s0:s0 + length] += sig
    elif kind == "shimmer":
        dur = 1.4
        length = min(int(dur * SR), buf_l.size - s0)
        t = np.arange(length) / SR
        env = np.exp(-t * 2.5) * (1.0 - np.exp(-t * 40.0))
        sig = (np.sin(2 * np.pi * 523.25 * t) * 0.5 + np.sin(2 * np.pi * 783.99 * t) * 0.35) * env * 0.16
        buf_l[s0:s0 + length] += sig
        buf_r[s0:s0 + length] += sig
    elif kind == "whoosh":
        dur = 1.1
        length = min(int(dur * SR), buf_l.size - s0)
        t = np.arange(length) / SR
        rng = np.random.default_rng(int(sec * 100))
        noise = rng.normal(0, 1, length)
        # Simple moving-average lowpass for soft wind whoosh
        kernel = np.ones(120) / 120.0
        soft = np.convolve(noise, kernel, mode="same")
        env = np.sin(np.pi * t / dur) ** 1.6
        sig = soft * env * 0.35
        buf_l[s0:s0 + length] += sig
        buf_r[s0:s0 + length] += sig
    elif kind == "tick":
        dur = 0.25
        length = min(int(dur * SR), buf_l.size - s0)
        t = np.arange(length) / SR
        env = np.exp(-t * 18.0)
        sig = np.sin(2 * np.pi * 880.0 * t) * env * 0.12
        buf_l[s0:s0 + length] += sig
        buf_r[s0:s0 + length] += sig


def generate_sfx_track(out_wav: Path) -> None:
    if out_wav.exists():
        return
    n = int(TOTAL_SEC * SR)
    left = np.zeros(n, dtype=np.float64)
    right = np.zeros(n, dtype=np.float64)

    events = [
        (0.45, "impact"),    # S01 buildings rise
        (1.80, "shimmer"),   # S01 paint
        (3.00, "whoosh"),    # B01 fly
        (12.0, "shimmer"),   # S02 Shinjuku paint
        (22.0, "whoosh"),    # B02
        (39.0, "whoosh"),    # B03
        (48.0, "impact"),    # S04 Hamura rise
        (56.0, "shimmer"),   # S04 paint
        (67.0, "whoosh"),    # B04
        (92.0, "whoosh"),    # B05
        (110.0, "whoosh"),   # B06
        (116.75, "tick"),    # S07 summer
        (119.50, "tick"),    # S07 autumn
        (122.25, "tick"),    # S07 winter
        (125.0, "tick"),     # S08 prompt
        (136.0, "whoosh"),   # B07
        (154.0, "impact"),   # S09 Hakodate rise
        (158.0, "shimmer"),  # S09 Hakodate paint
    ]
    for sec, kind in events:
        add_sfx(left, right, sec, kind)
    write_stereo_wav(out_wav, left, right)


def main() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # 1. VOICEVOX narration track
    n = int(TOTAL_SEC * SR)
    voice_buf = np.zeros(n, dtype=np.float64)
    for cid, offset, _disp, speech in NARRATION_LINES:
        wpath = AUDIO_DIR / f"voice_{cid}.wav"
        dur = synth_voicevox(speech, wpath)
        samples = read_wav_mono_48k(wpath)
        s0 = int(offset * SR)
        s1 = min(s0 + samples.size, n)
        voice_buf[s0:s1] += samples[: s1 - s0]
        print(f"voice {cid}: offset={offset}s dur={dur:.2f}s", flush=True)
    voice_track = AUDIO_DIR / "voice_track.wav"
    write_stereo_wav(voice_track, voice_buf, voice_buf)

    # 2. BGM + SFX
    bgm_wav = AUDIO_DIR / "bgm.wav"
    sfx_wav = AUDIO_DIR / "sfx.wav"
    generate_bgm(bgm_wav)
    generate_sfx_track(sfx_wav)

    # 3. Mix with sidechaincompress ducking + loudnorm (-14 LUFS)
    master_wav = AUDIO_DIR / "master_mix.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(voice_track),
            "-i", str(bgm_wav),
            "-i", str(sfx_wav),
            "-filter_complex",
            "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voice][v2];"
            "[voice]volume=-4dB[v1];"
            "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.38[m];"
            "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.65[sfx];"
            "[m][v2]sidechaincompress=threshold=0.03:ratio=7:attack=15:release=350[mc];"
            "[mc][v1][sfx]amix=inputs=3:weights=1 1 1:normalize=0[mix];"
            "[mix]loudnorm=I=-14:TP=-1.5:LRA=11[out]",
            "-map", "[out]",
            "-t", str(TOTAL_SEC),
            str(master_wav),
        ],
        check=True,
    )
    print(f"Master audio ready: {master_wav}", flush=True)


if __name__ == "__main__":
    main()
