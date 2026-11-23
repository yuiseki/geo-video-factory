#!/usr/bin/env python3
"""Generate 5.0-second seamless looping cinemagraph videos (locked camera; only ads,
neon signs, streetlights, vending machines, and wet-pavement reflections animate).
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
    synth_pad_chord,
    write_wav,
)


FPS = 24
DURATION = 5.0
N_FRAMES = int(FPS * DURATION)  # 120 frames


def make_soft_rect_mask(size: tuple[int, int], box: tuple[int, int, int, int], blur: float = 8.0) -> np.ndarray:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(box, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(radius=blur))
    return (np.asarray(m, dtype=np.float32) / 255.0)[..., None]


def generate_5s_loop_bgm(out_wav: Path) -> None:
    """2-chord dreamy 5.0s seamless loop (2.5s per chord)."""
    chords = [
        [40, 52, 56, 59, 63, 66],  # Emaj9
        [35, 47, 51, 54, 58, 61],  # Bmaj9
    ]
    total_samples = int(SAMPLE_RATE * DURATION)
    mix = np.zeros((total_samples, 2), dtype=np.float64)
    chord_dur = DURATION / len(chords)

    for i, midi_list in enumerate(chords):
        start = int(i * chord_dur * SAMPLE_RATE)
        pad = synth_pad_chord([midi_to_hz(m) for m in midi_list], chord_dur + 0.5, seed=50 + i)
        end = min(total_samples, start + pad.shape[0])
        mix[start:end] += pad[: end - start]
        overflow = start + pad.shape[0] - total_samples
        if overflow > 0:
            mix[:overflow] += pad[end - start :]

    rng = np.random.default_rng(77)
    t = np.arange(total_samples, dtype=np.float64) / SAMPLE_RATE
    hum = 0.008 * np.sin(2.0 * np.pi * 60.0 * t)
    hiss = lowpass_1pole(rng.normal(0.0, 0.005, total_samples), 1800.0)
    mix[:, 0] += hum + hiss
    mix[:, 1] += hum + hiss * 0.9

    mix = schroeder_reverb(mix, SAMPLE_RATE, wet=0.58)
    mix[:, 0] = lowpass_1pole(mix[:, 0], 2600.0)
    mix[:, 1] = lowpass_1pole(mix[:, 1], 2600.0)
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix * (0.82 / peak)
    write_wav(out_wav, mix)


def render_crossing_loop(src_png: Path, frames_dir: Path) -> None:
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
    # Road highlight mask for wet neon shimmer
    luma = (0.299 * base[..., 0] + 0.587 * base[..., 1] + 0.114 * base[..., 2]) / 255.0
    wet_mask = m_pavement * np.clip((luma[..., None] - 0.18) * 1.8, 0.0, 1.0)

    for idx in range(N_FRAMES):
        theta = 2.0 * math.pi * (idx / N_FRAMES)
        frame = base.copy()

        # 1. Top & bottom DHC billboards: periodic color shift + descending LED scan bar
        bar_y1 = 222 + ((idx * 2) % 90)
        scan1 = np.exp(-((yy - bar_y1) ** 2) / 36.0) * 26.0
        tint1 = np.array([
            1.0 + 0.12 * math.sin(theta),
            1.0 + 0.08 * math.sin(theta + 2.1),
            1.0 + 0.14 * math.cos(theta),
        ], dtype=np.float32)
        frame = frame * (1.0 - m_dhc_top) + (frame * tint1 + scan1) * m_dhc_top

        bar_y2 = 314 + (((idx + 45) * 2) % 95)
        scan2 = np.exp(-((yy - bar_y2) ** 2) / 36.0) * 22.0
        tint2 = np.array([
            1.0 + 0.14 * math.cos(theta * 2),
            1.0 + 0.10 * math.sin(theta * 2 + 1.0),
            1.0 + 0.12 * math.sin(theta),
        ], dtype=np.float32)
        frame = frame * (1.0 - m_dhc_bot) + (frame * tint2 + scan2) * m_dhc_bot

        # 2. Shibuya neon sign: periodic subtle flicker + brief 3-frame dip around frame 78
        flicker = 1.0 + 0.06 * math.sin(theta * 3) + 0.04 * math.sin(theta * 7)
        if 76 <= idx <= 79:
            flicker *= 0.62 if idx in (77, 78) else 0.80
        frame = frame * (1.0 - m_shibuya) + (frame * flicker) * m_shibuya

        # 3. Left small ads + Center-gai arch + QFRONT reflection pulse
        pulse = 1.0 + 0.09 * math.sin(theta + 0.6)
        frame = frame * (1.0 - m_left_ads) + (frame * pulse) * m_left_ads
        frame = frame * (1.0 - m_center_arch) + (frame * (1.0 + 0.08 * math.sin(theta * 2))) * m_center_arch
        frame = frame * (1.0 - m_qfront_glass) + (frame * (1.0 + 0.08 * math.sin(theta))) * m_qfront_glass

        # 4. Wet asphalt shimmer synchronized with billboard cycle
        shimmer = 1.0 + 0.10 * np.sin(theta * 2.0 + yy * 0.14)
        frame = frame * (1.0 - wet_mask) + (frame * shimmer) * wet_mask

        Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).save(frames_dir / f"frame_{idx:04d}.png")


def render_centergai_loop(src_png: Path, frames_dir: Path) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    base = np.asarray(Image.open(src_png).convert("RGB"), dtype=np.float32)
    H, W, _ = base.shape

    m_vending = make_soft_rect_mask((W, H), (826, 308, 924, 464), blur=6.0)
    m_vending_glow = make_soft_rect_mask((W, H), (760, 440, 960, 580), blur=28.0)
    m_streetlights = make_soft_rect_mask((W, H), (555, 220, 710, 390), blur=12.0)
    m_pavement = make_soft_rect_mask((W, H), (360, 410, 940, 720), blur=20.0)

    yy = np.arange(H, dtype=np.float32)[:, None, None]
    luma = (0.299 * base[..., 0] + 0.587 * base[..., 1] + 0.114 * base[..., 2]) / 255.0
    wet_mask = m_pavement * np.clip((luma[..., None] - 0.16) * 1.9, 0.0, 1.0)

    for idx in range(N_FRAMES):
        theta = 2.0 * math.pi * (idx / N_FRAMES)
        frame = base.copy()

        # 1. Vending machine fluorescent flicker (periodic, with a quick double-blink around frame 42)
        vf = 1.0 + 0.05 * math.sin(theta * 4)
        if idx in (41, 42, 45):
            vf *= 0.55 if idx != 42 else 0.78
        elif idx in (103, 104):
            vf *= 0.72
        frame = frame * (1.0 - m_vending) + (frame * vf) * m_vending
        frame = frame * (1.0 - m_vending_glow) + (frame * (0.94 + 0.06 * vf)) * m_vending_glow

        # 2. Distant streetlights & vertical signs gentle breathing
        sf = 1.0 + 0.08 * math.sin(theta * 2) + 0.03 * math.sin(theta * 5)
        frame = frame * (1.0 - m_streetlights) + (frame * sf) * m_streetlights

        # 3. Damp brick pavement reflection shimmer
        shimmer = 1.0 + 0.09 * np.sin(theta * 2.0 + yy * 0.12)
        frame = frame * (1.0 - wet_mask) + (frame * shimmer) * wet_mask

        Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).save(frames_dir / f"frame_{idx:04d}.png")


def encode_loop_mp4(frames_dir: Path, bgm_wav: Path, out_mp4: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-i", str(bgm_wav),
        "-filter_complex",
        "[0:v]rgbashift=rh=-1:bh=1,noise=alls=3:allf=t,format=yuv420p[v];"
        "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "17", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    flyover_dir = Path(__file__).resolve().parents[1]
    out_dir = flyover_dir / "out/cinemagraph_5s"
    out_dir.mkdir(parents=True, exist_ok=True)

    bgm_5s = flyover_dir / "assets/bgm/vaporwave_loop_5s.wav"
    generate_5s_loop_bgm(bgm_5s)
    print(f"Generated 5.0s seamless loop BGM: {bgm_5s}")

    c_frames = out_dir / "crossing_frames"
    render_crossing_loop(flyover_dir / "out/prototype_refs/proto_fp_crossing.png", c_frames)
    c_mp4 = out_dir / "shibuya_crossing_loop_5s.mp4"
    encode_loop_mp4(c_frames, bgm_5s, c_mp4)
    print(f"Encoded 5.0s crossing loop: {c_mp4}")

    g_frames = out_dir / "centergai_frames"
    render_centergai_loop(flyover_dir / "out/prototype_refs/proto_fp_centergai.png", g_frames)
    g_mp4 = out_dir / "shibuya_centergai_loop_5s.mp4"
    encode_loop_mp4(g_frames, bgm_5s, g_mp4)
    print(f"Encoded 5.0s centergai loop: {g_mp4}")


if __name__ == "__main__":
    main()
