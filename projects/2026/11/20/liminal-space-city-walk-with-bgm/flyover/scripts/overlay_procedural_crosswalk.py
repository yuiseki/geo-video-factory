#!/usr/bin/env python3
"""Deterministically draw crisp Shibuya Scramble Crossing zebra crosswalks,
fine wet-asphalt grain, and subtle neon reflections onto the 5120x3584 ground texture.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def draw_zebra(
    overlay: Image.Image,
    p1: tuple[float, float],
    p2: tuple[float, float],
    width_px: float,
    stripe_pitch_px: float = 13.0,
    stripe_fill_ratio: float = 0.52,
    alpha: int = 195,
) -> None:
    """Draw a deterministic zebra crosswalk between p1 and p2 on RGBA overlay."""
    draw = ImageDraw.Draw(overlay)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1.0:
        return
    ux, uy = dx / length, dy / length
    # Perpendicular unit vector
    nx, ny = -uy, ux
    half_w = width_px * 0.5
    bar_w = stripe_pitch_px * stripe_fill_ratio

    n_bars = int(length / stripe_pitch_px)
    for i in range(n_bars + 1):
        d0 = i * stripe_pitch_px
        d1 = min(length, d0 + bar_w)
        if d1 - d0 < 1.0:
            continue
        c0x, c0y = p1[0] + ux * d0, p1[1] + uy * d0
        c1x, c1y = p1[0] + ux * d1, p1[1] + uy * d1
        poly = [
            (c0x - nx * half_w, c0y - ny * half_w),
            (c1x - nx * half_w, c1y - ny * half_w),
            (c1x + nx * half_w, c1y + ny * half_w),
            (c0x + nx * half_w, c0y + ny * half_w),
        ]
        draw.polygon(poly, fill=(225, 228, 238, alpha))


def add_neon_glow(
    glow: Image.Image,
    center: tuple[float, float],
    radius: float,
    color: tuple[int, int, int],
    peak_alpha: int,
) -> None:
    draw = ImageDraw.Draw(glow)
    x, y = center
    for step in range(8, 0, -1):
        r = radius * (step / 8.0)
        a = int(peak_alpha * ((1.0 - (step - 1) / 8.0) ** 1.6) * 0.35)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(*color, a))


def tile_material(mat_path: Path, tile_px: int, width: int, height: int) -> Image.Image:
    """Tile a seamless ComfyUI material texture across (width, height)."""
    tile = Image.open(mat_path).convert("RGB").resize((tile_px, tile_px), Image.Resampling.LANCZOS)
    arr = np.asarray(tile)
    reps_y = math.ceil(height / tile_px)
    reps_x = math.ceil(width / tile_px)
    tiled = np.tile(arr, (reps_y, reps_x, 1))[:height, :width, :]
    return Image.fromarray(tiled)


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    ground_dir = project_dir / "assets/ground"
    mat_dir = project_dir / "assets/materials"
    base_path = ground_dir / "shibuya_crossing_sdxl_4x.png"
    base = Image.open(base_path).convert("RGB")
    W, H = base.size  # 5120, 3584

    asphalt_path = mat_dir / "mat_wet_asphalt.png"
    if asphalt_path.exists():
        asphalt = tile_material(asphalt_path, 256, W, H)
        base_arr = np.asarray(base, dtype=np.float32)
        asp_arr = np.asarray(asphalt, dtype=np.float32)
        # Preserve overall macro layout/luminance of base while injecting ComfyUI wet-asphalt grain
        asp_mean = float(asp_arr.mean())
        detail = asp_arr - asp_mean
        base = Image.fromarray(np.clip(base_arr * 0.78 + asp_arr * 0.22 + detail * 0.85, 0, 255).astype(np.uint8))

    # Exact pixel bounds from refine_crossing_ground.py
    orig_bbox = [139.6966552734375, 35.65841206428204, 139.7021484375, 35.66175941929504]
    crop_bbox = [139.6975, 35.6590, 139.7011, 35.6610]
    w_deg = orig_bbox[2] - orig_bbox[0]
    h_deg = orig_bbox[3] - orig_bbox[1]
    x0 = max(0, int(round((crop_bbox[0] - orig_bbox[0]) / w_deg * 1024)))
    x1 = min(1024, int(round((crop_bbox[2] - orig_bbox[0]) / w_deg * 1024)))
    y0 = max(0, int(round((orig_bbox[3] - crop_bbox[3]) / h_deg * 768)))
    y1 = min(768, int(round((orig_bbox[3] - crop_bbox[1]) / h_deg * 768)))

    def to_out(zx: float, zy: float) -> tuple[float, float]:
        return ((zx - x0) / (x1 - x0) * W, (zy - y0) / (y1 - y0) * H)

    scale_x = W / (x1 - x0)

    # 1. Deterministic zebra crosswalks measured from crossing_grid_ref.png
    zebra_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # Main diagonal Scramble crosswalk (Hachiko <-> QFRONT/Center-gai)
    draw_zebra(zebra_layer, to_out(748, 540), to_out(696, 492), width_px=15 * scale_x, stripe_pitch_px=24.0, alpha=190)
    # North crosswalk (Koen-dori / Inokashira-dori)
    draw_zebra(zebra_layer, to_out(724, 470), to_out(756, 480), width_px=13 * scale_x, stripe_pitch_px=22.0, alpha=175)
    # East crosswalk (JR Shibuya station side)
    draw_zebra(zebra_layer, to_out(765, 498), to_out(765, 542), width_px=16 * scale_x, stripe_pitch_px=22.0, alpha=175)
    # South crosswalk (Dogenzaka / 109 side)
    draw_zebra(zebra_layer, to_out(678, 540), to_out(736, 557), width_px=13 * scale_x, stripe_pitch_px=22.0, alpha=175)
    # West crosswalk (Bunkamura-dori side)
    draw_zebra(zebra_layer, to_out(664, 492), to_out(660, 526), width_px=14 * scale_x, stripe_pitch_px=22.0, alpha=175)

    # Slight anti-aliasing only so crosswalk stripes stay crisp at eye level
    zebra_layer = zebra_layer.filter(ImageFilter.GaussianBlur(radius=0.25))

    # 2. Wet asphalt specular neon reflections matching the real 3D billboards
    # Stretch reflections across the crossing & diagonal crosswalks toward camera
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    add_neon_glow(glow_layer, to_out(712, 488), 54 * scale_x, (240, 80, 195), 175)   # QFRONT magenta/red screen reflection
    add_neon_glow(glow_layer, to_out(724, 502), 48 * scale_x, (255, 170, 75), 160)   # QFRONT Starbucks/TSUTAYA warm glow
    add_neon_glow(glow_layer, to_out(736, 522), 50 * scale_x, (70, 195, 255), 165)   # Wet cyan sheen across main diagonal crosswalk
    add_neon_glow(glow_layer, to_out(720, 512), 46 * scale_x, (215, 95, 245), 155)   # Wet magenta sheen across main diagonal crosswalk
    add_neon_glow(glow_layer, to_out(686, 490), 50 * scale_x, (45, 180, 255), 175)   # Taiseido Hisamitsu/Salonpas cyan-blue
    add_neon_glow(glow_layer, to_out(692, 497), 38 * scale_x, (70, 245, 145), 140)   # Taiseido Salonpas green wash
    add_neon_glow(glow_layer, to_out(674, 498), 38 * scale_x, (255, 55, 85), 155)    # Sansenri / Center-gai red neon
    add_neon_glow(glow_layer, to_out(704, 528), 58 * scale_x, (85, 165, 245), 135)   # Foreground wet cyan reflection
    # 2.5 Deterministic Center-gai interlocking pavement & dim streetlight/vending glow
    deg_to_px_x = W / (crop_bbox[2] - crop_bbox[0])
    deg_to_px_y = H / (crop_bbox[3] - crop_bbox[1])

    def lonlat_to_out(lon: float, lat: float) -> tuple[float, float]:
        zx = (lon - orig_bbox[0]) / w_deg * 1024.0
        zy = (orig_bbox[3] - lat) / h_deg * 768.0
        return to_out(zx, zy)

    centergai_pts = [
        [139.700223, 35.659762],
        [139.699864, 35.660045],
        [139.699490, 35.660121],
        [139.699112, 35.660223],
        [139.698584, 35.660407],
        [139.697753, 35.660719],
    ]
    cg_px = [lonlat_to_out(lon, lat) for lon, lat in centergai_pts]
    pave_mask = Image.new("L", (W, H), 0)
    pave_draw = ImageDraw.Draw(pave_mask)
    pave_draw.line(cg_px, fill=190, width=int(24 * scale_x / 4.0))
    pave_mask = pave_mask.filter(ImageFilter.GaussianBlur(radius=4.0))

    brick_path = mat_dir / "mat_centergai_brick.png"
    if brick_path.exists():
        brick_rgb = tile_material(brick_path, 192, W, H)
        pave_layer = brick_rgb.convert("RGBA")
        pave_layer.putalpha(pave_mask)
    else:
        pave_layer = Image.new("RGBA", (W, H), (38, 34, 48, 0))
        pave_layer.putalpha(pave_mask)
    # Periodic dim streetlight / vending machine pools along Center-gai
    for i in range(len(cg_px) - 1):
        ax, ay = cg_px[i]
        bx, by = cg_px[i + 1]
        for frac, col in [(0.25, (110, 190, 255)), (0.65, (215, 110, 240))]:
            px = ax + (bx - ax) * frac
            py = ay + (by - ay) * frac
            add_neon_glow(glow_layer, (px, py), 16 * scale_x, col, 65)

    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=18.0))

    composed = Image.alpha_composite(base.convert("RGBA"), pave_layer)
    composed = Image.alpha_composite(composed, zebra_layer)
    # Composite neon wet sheen OVER zebra stripes too so wet crosswalk paint reflects cyan/magenta light
    composed = Image.alpha_composite(composed, glow_layer).convert("RGB")

    # 3. Deterministic fine wet-asphalt grain so ground never looks flat at 1.6m eye level
    rng = np.random.default_rng(2026)
    arr = np.asarray(composed, dtype=np.int16)
    grain = rng.normal(0.0, 5.5, size=(H, W, 1)).astype(np.int16)
    # Slight tire-wear modulation on crosswalk paint
    arr = np.clip(arr + grain, 0, 255).astype(np.uint8)
    final_im = Image.fromarray(arr)

    out_path = ground_dir / "shibuya_crossing_procedural_4x.png"
    final_im.save(out_path)
    print(f"Saved deterministic procedural crossing texture ({final_im.size}): {out_path}")


if __name__ == "__main__":
    main()
