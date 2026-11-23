#!/usr/bin/env python3
"""Generate 5 high-resolution orthographic building exterior textures for the
landmarks around Shibuya Scramble Crossing, leaving blank mounting frames
where real cropped billboards/signs will be placed in Three.js.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from PIL import Image, ImageDraw

from comfy_generate_materials import (
    build_controlnet_workflow,
    run_workflow,
    upload_image,
)


def make_qfront_canny(size: int = 1024) -> Image.Image:
    im = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    # Vertical curtain wall mullions
    for x in range(0, size, 64):
        draw.line([(x, 0), (x, size)], fill=(200, 200, 200), width=3)
    # Horizontal floor slabs
    for y in range(0, size, 128):
        draw.line([(0, y), (size, y)], fill=(255, 255, 255), width=5)
    # Blank giant LED screen recessed frame in upper-middle (256..768, 192..576)
    draw.rectangle([256, 192, 768, 576], fill=(0, 0, 0), outline=(255, 255, 255), width=6)
    return im


def make_taiseido_canny(size: int = 1024) -> Image.Image:
    im = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    # Structural concrete piers
    draw.rectangle([0, 0, 128, size], outline=(255, 255, 255), width=4)
    draw.rectangle([size - 128, 0, size - 1, size], outline=(255, 255, 255), width=4)
    # Floor bands
    for y in range(0, size, 170):
        draw.line([(0, y), (size, y)], fill=(255, 255, 255), width=5)
    # Blank central billboard bays (upper & lower)
    draw.rectangle([160, 120, 864, 460], fill=(0, 0, 0), outline=(255, 255, 255), width=5)
    draw.rectangle([160, 520, 864, 820], fill=(0, 0, 0), outline=(255, 255, 255), width=5)
    # Ground shutter zone
    for y in range(860, size, 24):
        draw.line([(128, y), (size - 128, y)], fill=(180, 180, 180), width=2)
    return im


def make_nishimura_canny(size: int = 1024) -> Image.Image:
    im = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    # Corner building piers & horizontal ribbon windows
    for x in [0, 96, size - 96, size - 1]:
        draw.line([(x, 0), (x, size)], fill=(255, 255, 255), width=4)
    for y in range(128, 840, 140):
        draw.rectangle([96, y, size - 96, y + 76], outline=(220, 220, 220), width=3)
        for mx in range(160, size - 96, 96):
            draw.line([(mx, y), (mx, y + 76)], fill=(160, 160, 160), width=2)
    # Blank horizontal fascia band at top for signage
    draw.rectangle([96, 16, size - 96, 112], fill=(0, 0, 0), outline=(255, 255, 255), width=4)
    # Ground shutter
    for y in range(860, size, 24):
        draw.line([(96, y), (size - 96, y)], fill=(180, 180, 180), width=2)
    return im


def make_seibu_canny(size: int = 1024) -> Image.Image:
    im = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    # Classic vertical concrete ribs of Shibuya Seibu
    for x in range(0, size, 48):
        draw.line([(x, 128), (x, 860)], fill=(230, 230, 230), width=3)
    # Upper blank parapet band
    draw.rectangle([0, 0, size - 1, 128], outline=(255, 255, 255), width=5)
    # Ground arcade
    draw.line([(0, 860), (size, 860)], fill=(255, 255, 255), width=6)
    for x in range(0, size, 128):
        draw.line([(x, 860), (x, size)], fill=(220, 220, 220), width=4)
    return im


def make_magnet_canny(size: int = 1024) -> Image.Image:
    im = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    # Dark aluminum & glass grid
    for x in range(0, size, 128):
        draw.line([(x, 0), (x, size)], fill=(220, 220, 220), width=4)
    for y in range(0, size, 128):
        draw.line([(0, y), (size, y)], fill=(220, 220, 220), width=4)
    # Blank recessed digital screen frame
    draw.rectangle([256, 256, 768, 640], fill=(0, 0, 0), outline=(255, 255, 255), width=6)
    return im


def main() -> None:
    flyover_dir = Path(__file__).resolve().parents[1]
    out_dir = flyover_dir / "assets/materials/facades"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_url = "http://127.0.0.1:8188"

    specs = [
        (
            "bldg_qfront_wall.png",
            4101,
            make_qfront_canny(),
            "flat orthographic architectural elevation texture of a modern Tokyo glass curtain wall building at 3am night, "
            "dark steel mullions and dark reflective glass panes with a large blank black matte steel mounting frame in the center, "
            "no text, no logos, no advertisements, no sky, edge-to-edge full frame",
            "text, letters, kanji, logos, advertisements, posters, neon signs, sky, street, perspective, vanishing point, people, blurry",
        ),
        (
            "bldg_taiseido_wall.png",
            4102,
            make_taiseido_canny(),
            "flat orthographic architectural elevation texture of a Japanese commercial building facade at 3am night, "
            "weathered dark grey concrete piers, closed grey metal roll-up shutter at the bottom, two large blank dark matte mounting panels in the center, "
            "no text, no logos, no advertisements, no sky, edge-to-edge full frame",
            "text, letters, kanji, logos, advertisements, posters, neon signs, sky, street, perspective, vanishing point, people, blurry",
        ),
        (
            "bldg_nishimura_wall.png",
            4103,
            make_nishimura_canny(),
            "flat orthographic architectural elevation texture of a multi-tenant Tokyo Shibuya corner building at 3am night, "
            "dark ceramic tile piers, dark horizontal office windows with dim interior ceiling lights, blank dark signboard frame at top, closed shutter at bottom, "
            "no text, no logos, no advertisements, no sky, edge-to-edge full frame",
            "text, letters, kanji, logos, advertisements, posters, neon signs, sky, street, perspective, vanishing point, people, blurry",
        ),
        (
            "bldg_seibu_wall.png",
            4104,
            make_seibu_canny(),
            "flat orthographic architectural elevation texture of a modernist Japanese department store facade at 3am night, "
            "vertical precast concrete ribs in dark cool grey tones, blank smooth upper parapet wall, dark closed ground-floor arcade, "
            "no text, no logos, no advertisements, no sky, edge-to-edge full frame",
            "text, letters, kanji, logos, advertisements, posters, neon signs, sky, street, perspective, vanishing point, people, blurry",
        ),
        (
            "bldg_magnet_wall.png",
            4105,
            make_magnet_canny(),
            "flat orthographic architectural elevation texture of a sleek dark aluminum and smoked glass commercial tower at 3am night, "
            "square metal cladding panels with a blank black recessed LED mounting frame in the center, "
            "no text, no logos, no advertisements, no sky, edge-to-edge full frame",
            "text, letters, kanji, logos, advertisements, posters, neon signs, sky, street, perspective, vanishing point, people, blurry",
        ),
    ]

    for fname, seed, canny_im, pos, neg in specs:
        out_path = out_dir / fname
        print(f"Generating {fname} (seed={seed})...")
        canny_name = upload_image(base_url, canny_im, f"{fname}_canny.png")
        wf = build_controlnet_workflow(pos, neg, seed=seed, canny_filename=canny_name, strength=0.78)
        im = run_workflow(base_url, wf)
        im.save(out_path)
        sha = hashlib.sha256(out_path.read_bytes()).hexdigest()[:12]
        print(f"Saved {out_path} (sha256={sha})")


if __name__ == "__main__":
    main()
