#!/usr/bin/env python3
"""Generate 10.0-second silent seamless looping CCTV / street-cam cinemagraphs
of deserted midnight Shibuya Scramble Crossing.
"""
from __future__ import annotations

import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_cinemagraph_10s import FPS, N_FRAMES, make_soft_rect_mask


def render_cctv_cam01_10s(src_png: Path, frames_dir: Path) -> None:
    """Elevated walkway roof CCTV camera looking over Scramble Crossing toward QFRONT & Center-gai."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    base = np.asarray(Image.open(src_png).convert("RGB"), dtype=np.float32)
    H, W, _ = base.shape

    m_dhc_bot = make_soft_rect_mask((W, H), (572, 290, 644, 372), blur=5.0)
    m_qfront = make_soft_rect_mask((W, H), (700, 110, 880, 340), blur=16.0)
    m_loccitane = make_soft_rect_mask((W, H), (10, 75, 195, 435), blur=12.0)
    m_right_neon = make_soft_rect_mask((W, H), (1008, 358, 1068, 430), blur=8.0)
    m_sig_left = make_soft_rect_mask((W, H), (235, 438, 255, 458), blur=4.0)
    m_sig_mid = make_soft_rect_mask((W, H), (640, 412, 658, 432), blur=4.0)
    m_sig_far = make_soft_rect_mask((W, H), (402, 345, 420, 365), blur=4.0)
    m_pavement = make_soft_rect_mask((W, H), (100, 400, 950, 700), blur=20.0)

    yy = np.arange(H, dtype=np.float32)[:, None, None]
    xx = np.arange(W, dtype=np.float32)[None, :, None]
    luma = (0.299 * base[..., 0] + 0.587 * base[..., 1] + 0.114 * base[..., 2]) / 255.0
    wet_mask = m_pavement * np.clip((luma[..., None] - 0.16) * 1.8, 0.0, 1.0)

    for idx in range(N_FRAMES):
        theta = 2.0 * math.pi * (idx / N_FRAMES)
        frame = base.copy()

        # 1. DHC lower screen scan + subtle color cycle
        bar_y = 290 + ((idx * 1.5) % 84)
        scan = np.exp(-((yy - bar_y) ** 2) / 30.0) * 24.0
        tint = np.array([
            1.0 + 0.13 * math.sin(theta * 2),
            1.0 + 0.09 * math.sin(theta * 2 + 2.0),
            1.0 + 0.14 * math.cos(theta * 2),
        ], dtype=np.float32)
        frame = frame * (1.0 - m_dhc_bot) + (frame * tint + scan) * m_dhc_bot

        # 2. QFRONT glass reflection, L'Occitane facade & right walkway neon pulse
        frame = frame * (1.0 - m_qfront) + (frame * (1.0 + 0.08 * math.sin(theta * 2))) * m_qfront
        frame = frame * (1.0 - m_loccitane) + (frame * (1.0 + 0.05 * math.sin(theta * 3 + 1.0))) * m_loccitane
        rf = 1.0 + 0.08 * math.sin(theta * 3)
        if idx in (110, 111, 113):
            rf *= 0.65
        frame = frame * (1.0 - m_right_neon) + (frame * rf) * m_right_neon

        # 3. Traffic light subtle pulse
        sig_pulse = 1.0 + 0.18 * math.sin(theta * 5)
        for ms in (m_sig_left, m_sig_mid, m_sig_far):
            frame = frame * (1.0 - ms) + (frame * sig_pulse) * ms

        # 4. Wet asphalt shimmer
        shimmer = 1.0 + 0.09 * np.sin(theta * 3.0 + yy * 0.11 + xx * 0.01)
        frame = frame * (1.0 - wet_mask) + (frame * shimmer) * wet_mask

        Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).save(frames_dir / f"frame_{idx:04d}.png")


def render_cctv_cam02_10s(src_png: Path, frames_dir: Path) -> None:
    """High-rise live-cam overlooking Scramble Crossing, Hachiko Square, and JR Shibuya Station."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    base = np.asarray(Image.open(src_png).convert("RGB"), dtype=np.float32)
    H, W, _ = base.shape

    m_station = make_soft_rect_mask((W, H), (485, 90, 1010, 180), blur=10.0)
    m_walkway = make_soft_rect_mask((W, H), (890, 195, 1060, 295), blur=10.0)
    m_signals = [
        make_soft_rect_mask((W, H), (505, 285, 535, 315), blur=5.0),
        make_soft_rect_mask((W, H), (798, 280, 828, 312), blur=5.0),
        make_soft_rect_mask((W, H), (942, 400, 976, 440), blur=6.0),
        make_soft_rect_mask((W, H), (502, 478, 530, 508), blur=5.0),
    ]
    m_pavement = make_soft_rect_mask((W, H), (440, 285, 1060, 715), blur=20.0)

    yy = np.arange(H, dtype=np.float32)[:, None, None]
    xx = np.arange(W, dtype=np.float32)[None, :, None]
    luma = (0.299 * base[..., 0] + 0.587 * base[..., 1] + 0.114 * base[..., 2]) / 255.0
    wet_mask = m_pavement * np.clip((luma[..., None] - 0.17) * 1.9, 0.0, 1.0)

    for idx in range(N_FRAMES):
        theta = 2.0 * math.pi * (idx / N_FRAMES)
        frame = base.copy()

        # 1. Station platform fluorescent lights subtle hum & 1 brief flicker
        st_f = 1.0 + 0.045 * math.sin(theta * 5) + 0.02 * math.sin(theta * 11)
        if idx in (134, 135, 137):
            st_f *= 0.70 if idx == 135 else 0.85
        frame = frame * (1.0 - m_station) + (frame * st_f) * m_station

        # 2. Elevated walkway lights gentle pulse
        wf = 1.0 + 0.06 * math.sin(theta * 2 + 0.5)
        frame = frame * (1.0 - m_walkway) + (frame * wf) * m_walkway

        # 3. Streetlights & traffic signals pulse
        sig_p = 1.0 + 0.18 * math.sin(theta * 4 + 1.1)
        for ms in m_signals:
            frame = frame * (1.0 - ms) + (frame * sig_p) * ms

        # 4. Wet asphalt shimmer
        shimmer = 1.0 + 0.09 * np.sin(theta * 3.0 + yy * 0.12 + xx * 0.01)
        frame = frame * (1.0 - wet_mask) + (frame * shimmer) * wet_mask

        Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8)).save(frames_dir / f"frame_{idx:04d}.png")


def encode_cctv_silent(frames_dir: Path, out_mp4: Path) -> None:
    # Subtle surveillance-cam look: crisp 1280x720, slight chromatic aberration, mild sensor grain, vignette
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-vf", "rgbashift=rh=-1:bh=1,eq=contrast=1.05:saturation=0.92,vignette=PI/4.8,noise=alls=4:allf=t,format=yuv420p",
        "-an",
        "-c:v", "libx264", "-crf", "17", "-preset", "medium",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    flyover_dir = Path(__file__).resolve().parents[1]
    out_dir = flyover_dir / "out/cinemagraph_10s"
    out_dir.mkdir(parents=True, exist_ok=True)

    cam01_frames = out_dir / "cctv_cam01_frames"
    render_cctv_cam01_10s(flyover_dir / "out/prototype_refs/proto_03s_crossing.png", cam01_frames)
    cam01_mp4 = out_dir / "shibuya_crossing_cctv_cam01_10s.mp4"
    encode_cctv_silent(cam01_frames, cam01_mp4)
    print(f"Encoded silent CCTV CAM-01 10s loop: {cam01_mp4}")

    cam02_frames = out_dir / "cctv_cam02_frames"
    render_cctv_cam02_10s(flyover_dir / "out/prototype_refs/proto_cctv_cam02.png", cam02_frames)
    cam02_mp4 = out_dir / "shibuya_crossing_cctv_cam02_10s.mp4"
    encode_cctv_silent(cam02_frames, cam02_mp4)
    print(f"Encoded silent CCTV CAM-02 10s loop: {cam02_mp4}")


if __name__ == "__main__":
    main()
