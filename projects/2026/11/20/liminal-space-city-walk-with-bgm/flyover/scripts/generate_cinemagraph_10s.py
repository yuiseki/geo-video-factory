#!/usr/bin/env python3
"""Generate a 10.0-second seamless looping cinemagraph of deserted midnight Shibuya Center-gai
(`shibuya_centergai_loop_10s.mp4`) informed by the lighting and wet brick pavement
characteristics of the reference night photo.
"""
from __future__ import annotations

import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_vaporwave_bgm import (
    SAMPLE_RATE,
    lowpass_1pole,
    midi_to_hz,
    schroeder_reverb,
    synth_bell_note,
    synth_pad_chord,
    write_wav,
)


FPS = 24
DURATION = 10.0
N_FRAMES = int(FPS * DURATION)  # 240 frames


def make_soft_rect_mask(size: tuple[int, int], box: tuple[int, int, int, int], blur: float = 8.0) -> np.ndarray:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(box, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(radius=blur))
    return (np.asarray(m, dtype=np.float32) / 255.0)[..., None]


def generate_10s_loop_bgm(out_wav: Path) -> None:
    """4-chord dreamy 10.0s seamless loop (2.5s per chord) with gentle chimes."""
    chords = [
        [40, 52, 56, 59, 63, 66],  # Emaj9
        [39, 51, 54, 58, 61],      # D#m7
        [37, 49, 52, 56, 59, 63],  # C#m9
        [35, 47, 51, 54, 58, 61],  # Bmaj9
    ]
    total_samples = int(SAMPLE_RATE * DURATION)
    mix = np.zeros((total_samples, 2), dtype=np.float64)
    chord_dur = DURATION / len(chords)

    for i, midi_list in enumerate(chords):
        start = int(i * chord_dur * SAMPLE_RATE)
        pad = synth_pad_chord([midi_to_hz(m) for m in midi_list], chord_dur + 0.5, seed=80 + i)
        end = min(total_samples, start + pad.shape[0])
        mix[start:end] += pad[: end - start]
        overflow = start + pad.shape[0] - total_samples
        if overflow > 0:
            mix[:overflow] += pad[end - start :]

    melody = [(0.6, 75, 2.2), (3.1, 73, 2.0), (5.6, 71, 2.2), (8.1, 68, 2.2)]
    for onset, midi, dur in melody:
        start = int(onset * SAMPLE_RATE)
        note = synth_bell_note(midi_to_hz(midi), dur)
        end = min(total_samples, start + note.shape[0])
        mix[start:end] += note[: end - start]
        overflow = start + note.shape[0] - total_samples
        if overflow > 0:
            mix[:overflow] += note[end - start :]

    rng = np.random.default_rng(108)
    t = np.arange(total_samples, dtype=np.float64) / SAMPLE_RATE
    hum = 0.008 * np.sin(2.0 * np.pi * 60.0 * t) + 0.003 * np.sin(2.0 * np.pi * 120.0 * t)
    hiss = lowpass_1pole(rng.normal(0.0, 0.005, total_samples), 1800.0)
    mix[:, 0] += hum + hiss
    mix[:, 1] += hum + hiss * 0.9

    mix = schroeder_reverb(mix, SAMPLE_RATE, wet=0.58)
    mix[:, 0] = lowpass_1pole(mix[:, 0], 2700.0)
    mix[:, 1] = lowpass_1pole(mix[:, 1], 2700.0)
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix * (0.82 / peak)
    write_wav(out_wav, mix)


def render_centergai_10s(src_png: Path, frames_dir: Path) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    base = np.asarray(Image.open(src_png).convert("RGB"), dtype=np.float32)
    H, W, _ = base.shape

    # Masks mapped from grid_proto_fp_centergai.png
    m_vending = make_soft_rect_mask((W, H), (826, 308, 924, 464), blur=6.0)
    m_vending_glow = make_soft_rect_mask((W, H), (745, 435, 975, 595), blur=30.0)
    m_left_ramen = make_soft_rect_mask((W, H), (495, 130, 565, 345), blur=8.0)
    m_right_karaoke = make_soft_rect_mask((W, H), (702, 192, 742, 318), blur=6.0)
    m_streetlights = make_soft_rect_mask((W, H), (555, 220, 705, 390), blur=14.0)
    m_pavement = make_soft_rect_mask((W, H), (330, 405, 960, 720), blur=22.0)

    yy = np.arange(H, dtype=np.float32)[:, None, None]
    xx = np.arange(W, dtype=np.float32)[None, :, None]
    luma = (0.299 * base[..., 0] + 0.587 * base[..., 1] + 0.114 * base[..., 2]) / 255.0
    wet_mask = m_pavement * np.clip((luma[..., None] - 0.15) * 2.0, 0.0, 1.0)

    for idx in range(N_FRAMES):
        theta = 2.0 * math.pi * (idx / N_FRAMES)
        frame = base.copy()

        # 1. Vending machine fluorescent tube flicker (2 subtle fault bursts in 10s)
        vf = 1.0 + 0.045 * math.sin(theta * 5) + 0.025 * math.sin(theta * 11)
        if idx in (75, 76, 78, 79, 186, 187, 190):
            vf *= 0.54 if idx in (76, 79, 186) else 0.78
        frame = frame * (1.0 - m_vending) + (frame * vf) * m_vending
        frame = frame * (1.0 - m_vending_glow) + (frame * (0.93 + 0.07 * vf)) * m_vending_glow

        # 2. Left ramen/izakaya vertical sign & right karaoke red sign gentle pulse
        lf = 1.0 + 0.09 * math.sin(theta * 2 + 0.4)
        rf = 1.0 + 0.11 * math.sin(theta * 3 + 1.8)
        frame = frame * (1.0 - m_left_ramen) + (frame * lf) * m_left_ramen
        frame = frame * (1.0 - m_right_karaoke) + (frame * rf) * m_right_karaoke

        # 3. Distant streetlights & mist glow
        sf = 1.0 + 0.08 * math.sin(theta * 2) + 0.03 * math.sin(theta * 7)
        frame = frame * (1.0 - m_streetlights) + (frame * sf) * m_streetlights

        # 4. Damp brick pavement reflection shimmer (vertical light streaks + subtle warm/cool balance)
        shimmer = 1.0 + 0.10 * np.sin(theta * 3.0 + yy * 0.11 + xx * 0.015)
        frame = frame * (1.0 - wet_mask) + (frame * shimmer) * wet_mask

        Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).save(frames_dir / f"frame_{idx:04d}.png")


def render_crossing_10s(src_png: Path, frames_dir: Path) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    base = np.asarray(Image.open(src_png).convert("RGB"), dtype=np.float32)
    H, W, _ = base.shape

    m_dhc_top = make_soft_rect_mask((W, H), (436, 222, 570, 304), blur=5.0)
    m_dhc_bot = make_soft_rect_mask((W, H), (445, 314, 567, 405), blur=5.0)
    m_shibuya = make_soft_rect_mask((W, H), (247, 114, 376, 232), blur=7.0)
    m_left_ads = make_soft_rect_mask((W, H), (275, 315, 365, 420), blur=8.0)
    m_qfront_glass = make_soft_rect_mask((W, H), (830, 120, 960, 330), blur=18.0)
    m_center_arch = make_soft_rect_mask((W, H), (590, 320, 745, 455), blur=14.0)
    m_pavement = make_soft_rect_mask((W, H), (0, 470, 1280, 720), blur=16.0)

    yy = np.arange(H, dtype=np.float32)[:, None, None]
    xx = np.arange(W, dtype=np.float32)[None, :, None]
    luma = (0.299 * base[..., 0] + 0.587 * base[..., 1] + 0.114 * base[..., 2]) / 255.0
    wet_mask = m_pavement * np.clip((luma[..., None] - 0.18) * 1.8, 0.0, 1.0)

    for idx in range(N_FRAMES):
        theta = 2.0 * math.pi * (idx / N_FRAMES)
        frame = base.copy()

        # 1. Top & bottom DHC billboards: periodic color shift + descending LED scan bar
        bar_y1 = 222 + ((idx * 1.5) % 90)
        scan1 = np.exp(-((yy - bar_y1) ** 2) / 36.0) * 24.0
        tint1 = np.array([
            1.0 + 0.12 * math.sin(theta * 2),
            1.0 + 0.08 * math.sin(theta * 2 + 2.1),
            1.0 + 0.14 * math.cos(theta * 2),
        ], dtype=np.float32)
        frame = frame * (1.0 - m_dhc_top) + (frame * tint1 + scan1) * m_dhc_top

        bar_y2 = 314 + (((idx + 60) * 1.5) % 95)
        scan2 = np.exp(-((yy - bar_y2) ** 2) / 36.0) * 20.0
        tint2 = np.array([
            1.0 + 0.14 * math.cos(theta * 3),
            1.0 + 0.10 * math.sin(theta * 3 + 1.0),
            1.0 + 0.12 * math.sin(theta * 2),
        ], dtype=np.float32)
        frame = frame * (1.0 - m_dhc_bot) + (frame * tint2 + scan2) * m_dhc_bot

        # 2. Shibuya neon sign: periodic subtle flicker + 2 brief fault bursts in 10s
        flicker = 1.0 + 0.05 * math.sin(theta * 4) + 0.03 * math.sin(theta * 9)
        if idx in (78, 79, 81, 192, 193, 194):
            flicker *= 0.60 if idx in (79, 193) else 0.80
        frame = frame * (1.0 - m_shibuya) + (frame * flicker) * m_shibuya

        # 3. Left small ads + Center-gai arch + QFRONT reflection pulse
        frame = frame * (1.0 - m_left_ads) + (frame * (1.0 + 0.09 * math.sin(theta * 2 + 0.6))) * m_left_ads
        frame = frame * (1.0 - m_center_arch) + (frame * (1.0 + 0.08 * math.sin(theta * 3))) * m_center_arch
        frame = frame * (1.0 - m_qfront_glass) + (frame * (1.0 + 0.08 * math.sin(theta * 2))) * m_qfront_glass

        # 4. Wet asphalt shimmer synchronized with billboard cycle
        shimmer = 1.0 + 0.10 * np.sin(theta * 3.0 + yy * 0.13 + xx * 0.012)
        frame = frame * (1.0 - wet_mask) + (frame * shimmer) * wet_mask

        Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).save(frames_dir / f"frame_{idx:04d}.png")


def encode_10s_mp4(frames_dir: Path, out_mp4: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-vf", "rgbashift=rh=-1:bh=1,vignette=PI/5.5,noise=alls=3:allf=t,format=yuv420p",
        "-an",
        "-c:v", "libx264", "-crf", "17", "-preset", "medium",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    flyover_dir = Path(__file__).resolve().parents[1]
    out_dir = flyover_dir / "out/cinemagraph_10s"
    out_dir.mkdir(parents=True, exist_ok=True)

    frames_dir = out_dir / "centergai_frames"
    render_centergai_10s(flyover_dir / "out/prototype_refs/proto_fp_centergai.png", frames_dir)
    out_mp4 = out_dir / "shibuya_centergai_loop_10s.mp4"
    encode_10s_mp4(frames_dir, out_mp4)
    print(f"Encoded 10.0s silent centergai loop: {out_mp4}")

    c_frames_dir = out_dir / "crossing_frames"
    render_crossing_10s(flyover_dir / "out/prototype_refs/proto_fp_crossing.png", c_frames_dir)
    c_mp4 = out_dir / "shibuya_crossing_loop_10s.mp4"
    encode_10s_mp4(c_frames_dir, c_mp4)
    print(f"Encoded 10.0s silent crossing loop: {c_mp4}")


if __name__ == "__main__":
    main()
