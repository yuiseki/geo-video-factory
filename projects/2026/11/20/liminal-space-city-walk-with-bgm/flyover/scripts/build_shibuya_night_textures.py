#!/usr/bin/env python3
"""Generate ComfyUI building facade textures (including L'Occitane Shibuya Ekimae
Building / Oosoto Building) and crop/perspective-rectify real night billboards &
storefronts from the collected night photography corpus.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

from comfy_generate_materials import (
    build_controlnet_workflow,
    run_workflow,
    upload_image,
)


def find_homography(src_pts: list[tuple[float, float]], dst_w: int, dst_h: int) -> tuple[float, ...]:
    """Compute PIL Image.transform(PERSPECTIVE) 8-tuple mapping dst -> src."""
    dst_pts = [(0.0, 0.0), (float(dst_w - 1), 0.0), (float(dst_w - 1), float(dst_h - 1)), (0.0, float(dst_h - 1))]
    A = []
    B = []
    for (x, y), (u, v) in zip(dst_pts, src_pts):
        A.append([x, y, 1, 0, 0, 0, -x * u, -y * u])
        A.append([0, 0, 0, x, y, 1, -x * v, -y * v])
        B.append(u)
        B.append(v)
    A_mat = np.array(A, dtype=np.float64)
    B_vec = np.array(B, dtype=np.float64)
    coeffs = np.linalg.solve(A_mat, B_vec)
    return tuple(float(c) for c in coeffs)


def warp_quad_pil(
    im: Image.Image,
    src_pts: list[tuple[float, float]],
    out_w: int,
    out_h: int,
    contrast: float = 1.08,
    color: float = 1.08,
) -> Image.Image:
    coeffs = find_homography(src_pts, out_w, out_h)
    warped = im.transform((out_w, out_h), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC)
    if contrast != 1.0:
        warped = ImageEnhance.Contrast(warped).enhance(contrast)
    if color != 1.0:
        warped = ImageEnhance.Color(warped).enhance(color)
    return warped


def make_loccitane_canny(size: int = 1024) -> Image.Image:
    """Architectural Canny blueprint for L'Occitane / Shibuya Ekimae Building:
    - Bottom 32% (y=696..1024): Golden yellow L'Occitane 1F-3F facade frames with big warm cafe windows
    - Upper 68% (y=0..696): Dark smoked-glass & terracotta tile grid with horizontal floor bands
    """
    im = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    # Vertical mullions
    for x in range(0, size, 128):
        draw.line([(x, 0), (x, size)], fill=(230, 230, 230), width=4)
    # Upper floor slabs (4F-9F)
    for y in range(0, 696, 116):
        draw.line([(0, y), (size, y)], fill=(255, 255, 255), width=5)
        for x in range(16, size - 16, 128):
            draw.rectangle([x, y + 14, min(x + 100, size - 8), y + 102], outline=(190, 190, 190), width=2)
    # Strong divider between 3F L'Occitane and 4F
    draw.line([(0, 696), (size, 696)], fill=(255, 255, 255), width=8)
    # Lower 1F-3F L'Occitane Provence golden frame & arched/grid cafe windows
    for y in [696, 805, 915]:
        draw.line([(0, y), (size, y)], fill=(255, 255, 255), width=6)
        for x in range(20, size - 20, 128):
            draw.rectangle([x, y + 12, min(x + 92, size - 12), y + 96], outline=(240, 240, 240), width=3)
    return im


def generate_loccitane_comfy_wall(base_url: str, materials_dir: Path) -> Image.Image:
    out_path = materials_dir / "bldg_loccitane_wall.png"
    canny = make_loccitane_canny(1024)
    canny_name = upload_image(base_url, canny, "bldg_loccitane_canny.png")
    pos = (
        "flat orthographic architectural elevation texture of Shibuya Ekimae commercial building at 3am night, "
        "lower three floors have warm Provence golden yellow architectural cladding panels and glowing warm amber cafe windows, "
        "upper six floors have dark charcoal glass curtain wall and dark terracotta tile grid with warm interior lights, "
        "photorealistic architectural facade texture, no text, no logos, no sky, edge-to-edge full frame"
    )
    neg = "text, letters, kanji, logos, sky, street, cars, people, perspective, vanishing point, blurry"
    print("Generating bldg_loccitane_wall.png via ComfyUI ControlNet (seed=4301)...")
    wf = build_controlnet_workflow(pos, neg, seed=4301, canny_filename=canny_name, strength=0.80)
    im = run_workflow(base_url, wf).convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)

    # Reinforce the iconic Provence golden yellow lower 32% & warm window glow so even unwrapped side walls read unmistakably as L'Occitane
    arr = np.array(im, dtype=np.float32)
    # Upper floors (0..696): sleek dark warm charcoal glass + subtle warm window grid
    arr[:696, :, 0] *= 0.58
    arr[:696, :, 1] *= 0.52
    arr[:696, :, 2] *= 0.50
    # Lower floors (696..1024): warm Provence gold frame + amber cafe glow
    gold_tint = np.array([235.0, 172.0, 42.0], dtype=np.float32)
    lower = arr[696:, :, :]
    luma = (0.299 * lower[:, :, 0] + 0.587 * lower[:, :, 1] + 0.114 * lower[:, :, 2]) / 255.0
    lower_tinted = lower * 0.45 + gold_tint[None, None, :] * (0.35 + 0.55 * luma[:, :, None])
    arr[696:, :, :] = np.clip(lower_tinted, 0, 255)

    out_im = Image.fromarray(arr.astype(np.uint8))
    out_im.save(out_path)
    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()[:12]
    print(f"Saved {out_path.name} (sha256={sha})")
    return out_im


def pack_facades_atlas(materials_dir: Path, loccitane_im: Image.Image) -> None:
    """Update slot 5 of facades_atlas.png (3072x2048 3x2) with bldg_loccitane_wall.png."""
    atlas_path = materials_dir / "facades_atlas.png"
    atlas = Image.open(atlas_path).convert("RGB")
    # Slot 5 is col=2, row=1 -> (2048, 1024)
    atlas.paste(loccitane_im, (2048, 1024))
    atlas.save(atlas_path)
    print("Updated slot 5 (col=2, row=1) of facades_atlas.png with bldg_loccitane_wall.png")


def crop_all_night_billboards(flyover_dir: Path) -> None:
    crossing_dir = flyover_dir / "assets/photos/shibuya_crossing"
    night_dir = flyover_dir / "assets/photos/shibuya_buildings_night"
    out_dir = flyover_dir / "assets/billboards"
    out_dir.mkdir(parents=True, exist_ok=True)

    im_034_4k = Image.open(night_dir / "034_2026_2_27_202602272115_IMG_2370.jpg").convert("RGB")
    im_005 = Image.open(crossing_dir / "005_Shibuya_2016-03_26124083992.jpg").convert("RGB")
    im_009 = Image.open(crossing_dir / "009_Shibuya_Crossing_May_2017_1.jpg").convert("RGB")
    im_052 = Image.open(crossing_dir / "052_Shibuya_Tokyo_Japan_48847062017.jpg").convert("RGB")
    im_019_mag = Image.open(night_dir / "019_MAGNET_by_SHIBUYA_109_2026_2_27_202602272115_IMG_2369.jpg").convert("RGB")
    im_047 = Image.open(crossing_dir / "047_Tokyo_16230379595_b.jpg").convert("RGB")
    im_177_qf = Image.open(night_dir / "177_Q-Front_2012.jpg").convert("RGB")
    im_147_tokyu = Image.open(night_dir / "147_Tokyu_Department_Store_Shibuya_Toyoko_2018.jpg").convert("RGB")

    # 1. L'Occitane 1F-3F golden storefront + 4F USHIHACHI from 2026 4K night photo (034_2026_2_27... 3840x2880)
    # NE corner + E face lower 1F-4F (no tree obstruction!)
    loc_lower = warp_quad_pil(
        im_034_4k,
        [(1340, 560), (2135, 535), (2120, 1555), (1320, 1545)],
        768,
        768,
        contrast=1.12,
        color=1.14,
    )
    loc_lower.save(out_dir / "sign_loccitane_cafe_4k.png")
    print("Saved sign_loccitane_cafe_4k.png")

    # 2. L'Occitane upper 6F-9F tenant signs (しゃぶ葉 / プライスコンタクト / Caféレストラン ガスト / AEON 英会話イーオン)
    # From 009 (1920x1280) darkened to night luminance & boosted neon contrast, combined with 005 night glow
    upper_009 = warp_quad_pil(
        im_009,
        [(235, 412), (618, 412), (612, 668), (225, 665)],
        768,
        512,
        contrast=1.22,
        color=1.20,
    )
    upper_005 = warp_quad_pil(
        im_005,
        [(245, 185), (688, 195), (682, 500), (235, 492)],
        768,
        512,
        contrast=1.18,
        color=1.18,
    )
    # Blend 65% sharp 009 signage (しゃぶ葉/プライスコンタクト/ガスト/イーオン) with 35% night lighting from 005
    arr_009 = np.array(upper_009, dtype=np.float32) * 0.78
    arr_005 = np.array(upper_005, dtype=np.float32)
    upper_blend = np.clip(arr_009 * 0.65 + arr_005 * 0.35, 0, 255).astype(np.uint8)
    Image.fromarray(upper_blend).save(out_dir / "sign_loccitane_upper.png")
    print("Saved sign_loccitane_upper.png")

    # 3. Composite full NE corner facade of Shibuya Ekimae Building (1F-9F: L'Occitane + USHIHACHI + Gusto + Price Contact + Shabuyo)
    full_ne = Image.new("RGB", (768, 1280))
    full_ne.paste(Image.fromarray(upper_blend), (0, 0))
    full_ne.paste(loc_lower, (0, 512))
    full_ne.save(out_dir / "sign_loccitane_ne_full.png")
    print("Saved sign_loccitane_ne_full.png")

    # 4. Tall vertical pillar banner on NW edge of L'Occitane building (17LIVE red night banner from 034_4k)
    loc_banner = warp_quad_pil(
        im_034_4k,
        [(2145, 10), (2455, 10), (2450, 1295), (2135, 1295)],
        256,
        1024,
        contrast=1.10,
        color=1.12,
    )
    loc_banner.save(out_dir / "sign_loccitane_banner.png")
    print("Saved sign_loccitane_banner.png")

    # 5. Dogenzaka North side wall of Shibuya Ekimae Building (Red-brown tile + 7F Gusto + 6F AGA + SunDrug + Acom 3F + LUSH)
    loc_north = warp_quad_pil(
        im_034_4k,
        [(2475, 15), (3210, 290), (3190, 1520), (2465, 1460)],
        768,
        1024,
        contrast=1.12,
        color=1.14,
    )
    loc_north.save(out_dir / "sign_loccitane_dogenzaka.png")
    print("Saved sign_loccitane_dogenzaka.png")

    # 6. Oosoto Building (East face adjacent to L'Occitane: cyan eyecity banner + red/white grid + Shinagawa Skin Clinic + vertical sleeve signs)
    oosoto_sleeves = warp_quad_pil(
        im_034_4k,
        [(1215, 20), (1325, 20), (1315, 1420), (1210, 1420)],
        192,
        1024,
        contrast=1.15,
        color=1.15,
    )
    oosoto_sleeves.save(out_dir / "sign_oosoto_sleeves.png")

    eyecity = warp_quad_pil(
        im_005,
        [(130, 228), (222, 232), (215, 620), (122, 615)],
        256,
        768,
        contrast=1.16,
        color=1.18,
    )
    eyecity.save(out_dir / "sign_eyecity_blue.png")
    print("Saved sign_oosoto_sleeves.png & sign_eyecity_blue.png")

    # 7. Rooftop billboard of Shibuya Ekimae Building (from 005 night photo)
    loc_roof = warp_quad_pil(
        im_005,
        [(312, 2), (812, 18), (808, 172), (308, 145)],
        768,
        280,
        contrast=1.14,
        color=1.12,
    )
    loc_roof.save(out_dir / "sign_loccitane_roof.png")
    print("Saved sign_loccitane_roof.png")

    # 8. MAGNET by SHIBUYA109 (from 2026 4K night photo 019_MAGNET... & 047 consumer finance tower)
    magnet_west = warp_quad_pil(
        im_019_mag,
        [(640, 820), (2085, 680), (2070, 2120), (630, 2150)],
        1024,
        768,
        contrast=1.14,
        color=1.14,
    )
    magnet_west.save(out_dir / "sign_magnet_west_4k.png")

    magnet_corner = warp_quad_pil(
        im_019_mag,
        [(2085, 675), (2635, 695), (2625, 2520), (2075, 2480)],
        512,
        1024,
        contrast=1.15,
        color=1.16,
    )
    magnet_corner.save(out_dir / "sign_magnet_corner_4k.png")

    eirai_tower = warp_quad_pil(
        im_047,
        [(1628, 15), (1752, 15), (1748, 785), (1625, 785)],
        256,
        1024,
        contrast=1.12,
        color=1.10,
    )
    eirai_tower.save(out_dir / "sign_acom_lake_aiful.png")
    print("Saved MAGNET 4K & Acom/Lake/Aiful tower billboards")

    # 9. Tokyu Toyoko West Building diamond lattice facade (south side of Hachiko Square)
    tokyu_west = warp_quad_pil(
        im_147_tokyu,
        [(1040, 480), (2040, 520), (2020, 1400), (1020, 1390)],
        1024,
        640,
        contrast=1.14,
        color=1.12,
    )
    tokyu_west.save(out_dir / "sign_tokyu_west_facade.png")
    print("Saved sign_tokyu_west_facade.png")


def main() -> None:
    flyover_dir = Path(__file__).resolve().parents[1]
    materials_dir = flyover_dir / "assets/materials"
    base_url = "http://127.0.0.1:8188"

    loc_im = generate_loccitane_comfy_wall(base_url, materials_dir)
    pack_facades_atlas(materials_dir, loc_im)
    crop_all_night_billboards(flyover_dir)
    print("All Shibuya night textures and billboards built successfully!")


if __name__ == "__main__":
    main()
