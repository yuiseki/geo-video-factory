#!/usr/bin/env python3
"""Crop the Scramble Crossing + Center-gai corridor from the GSI z18 mosaic,
refine it with SDXL + ControlNet Tile via ComfyUI API, and upscale 4x with RealESRGAN.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from PIL import Image, ImageEnhance
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_refine_textures import build_sdxl_tile_workflow, run_workflow, upload_image
from upscale_shibuya_assets import load_upscaler, upscale_pil_tiled


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    ground_dir = project_dir / "assets/ground"
    src_path = ground_dir / "shibuya_ortho_z18.png"

    # Original mosaic exact bbox: [west, south, east, north]
    orig_bbox = [139.6966552734375, 35.65841206428204, 139.7021484375, 35.66175941929504]
    w_deg = orig_bbox[2] - orig_bbox[0]
    h_deg = orig_bbox[3] - orig_bbox[1]

    im = Image.open(src_path).convert("RGB")
    W, H = im.size  # 1024, 768

    # Tight corridor around Scramble Crossing & Center-gai:
    # lon: [139.6975, 139.7011], lat: [35.6590, 35.6610]
    crop_bbox = [139.6975, 35.6590, 139.7011, 35.6610]
    x0 = max(0, int(round((crop_bbox[0] - orig_bbox[0]) / w_deg * W)))
    x1 = min(W, int(round((crop_bbox[2] - orig_bbox[0]) / w_deg * W)))
    y0 = max(0, int(round((orig_bbox[3] - crop_bbox[3]) / h_deg * H)))
    y1 = min(H, int(round((orig_bbox[3] - crop_bbox[1]) / h_deg * H)))

    # Recompute exact bbox matching integer pixel crop
    exact_crop_bbox = [
        orig_bbox[0] + (x0 / W) * w_deg,
        orig_bbox[3] - (y1 / H) * h_deg,
        orig_bbox[0] + (x1 / W) * w_deg,
        orig_bbox[3] - (y0 / H) * h_deg,
    ]

    cropped = im.crop((x0, y0, x1, y1))
    sdxl_in = cropped.resize((1280, 896), Image.Resampling.LANCZOS)
    sdxl_in = ImageEnhance.Brightness(sdxl_in).enhance(0.30)
    sdxl_in = ImageEnhance.Contrast(sdxl_in).enhance(1.25)

    in_path = ground_dir / "shibuya_crossing_sdxl_in.png"
    sdxl_in.save(in_path)

    base_url = "http://127.0.0.1:8188"
    uploaded = upload_image(base_url, in_path, "shibuya_crossing_sdxl_in.png")
    wf = build_sdxl_tile_workflow(
        uploaded,
        positive=(
            "top-down aerial orthophoto of deserted Tokyo Shibuya Scramble Crossing at 3am midnight, "
            "dark wet asphalt road surface with realistic fine grain, crisp sharp bright white crosswalk stripes, "
            "subtle cyan and purple neon reflections on damp pavement, zero cars, zero people, ultra detailed"
        ),
        negative=(
            "cars, vehicles, buses, taxis, pedestrians, people, crowds, daytime sunlight, "
            "blurry, lowres, jpeg artifacts, watermark, text"
        ),
        denoise=0.64,
        cn_strength=0.82,
        steps=24,
        cfg=6.8,
        seed=303,
    )
    print(f"Running SDXL + ControlNet Tile on tight crop {cropped.size} -> (1280, 896)...")
    refined = run_workflow(base_url, wf)
    sdxl_out = ground_dir / "shibuya_crossing_sdxl.png"
    refined.save(sdxl_out)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = load_upscaler(Path.home() / "ComfyUI/models/upscale_models/RealESRGAN_x4plus.pth", device)
    up = upscale_pil_tiled(refined, model, device, tile_size=512, overlap=32)
    up_out = ground_dir / "shibuya_crossing_sdxl_4x.png"
    up.save(up_out)

    meta = {"bbox": exact_crop_bbox, "size": list(up.size)}
    (ground_dir / "crossing_ground_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Saved 4x tight ground ({up.size}): {up_out}, bbox={exact_crop_bbox}")


if __name__ == "__main__":
    main()
