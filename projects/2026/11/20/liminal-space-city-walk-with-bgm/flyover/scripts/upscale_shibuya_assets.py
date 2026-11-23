#!/usr/bin/env python3
"""Fetch Shibuya GSI seamlessphoto tiles, upscale them (super-resolution),
and upscale PLATEAU GLB textures using RealESRGAN_x4plus (BSD-3-Clause) on MPS/CUDA/CPU.
"""
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path
import struct
import time
import urllib.request

import numpy as np
from PIL import Image
import spandrel
import torch


USER_AGENT = "GeoVideoFactoryUpscaler/1.0 (https://github.com/yuiseki/geo-video-factory)"
GSI_TILE_URL = "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg"


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def num2deg(xtile: int, ytile: int, zoom: int) -> tuple[float, float]:
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def fetch_gsi_mosaic(bbox: list[float], zoom: int, out_dir: Path) -> tuple[Path, list[float]]:
    """Fetch GSI seamlessphoto tiles covering bbox [west, south, east, north] and stitch them."""
    west, south, east, north = bbox
    x_min, y_min = deg2num(north, west, zoom)
    x_max, y_max = deg2num(south, east, zoom)

    cols = x_max - x_min + 1
    rows = y_max - y_min + 1
    mosaic = Image.new("RGB", (cols * 256, rows * 256))

    cache_dir = out_dir / f"tiles_z{zoom}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    for tx in range(x_min, x_max + 1):
        for ty in range(y_min, y_max + 1):
            tile_file = cache_dir / f"{tx}_{ty}.jpg"
            if not tile_file.exists():
                url = GSI_TILE_URL.format(z=zoom, x=tx, y=ty)
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    tile_file.write_bytes(resp.read())
                time.sleep(0.05)
            im = Image.open(tile_file).convert("RGB")
            mosaic.paste(im, ((tx - x_min) * 256, (ty - y_min) * 256))

    north_bound, west_bound = num2deg(x_min, y_min, zoom)[0], num2deg(x_min, y_min, zoom)[1]
    south_bound, east_bound = num2deg(x_max + 1, y_max + 1, zoom)[0], num2deg(x_max + 1, y_max + 1, zoom)[1]
    exact_bbox = [west_bound, south_bound, east_bound, north_bound]

    out_path = out_dir / f"shibuya_ortho_z{zoom}.png"
    mosaic.save(out_path)
    print(f"stitched GSI z{zoom} mosaic: {mosaic.size} -> {out_path}, bbox={exact_bbox}")
    return out_path, exact_bbox


def load_upscaler(model_path: Path, device: str):
    loader = spandrel.ModelLoader(device=torch.device(device))
    model = loader.load_from_file(model_path)
    model.eval()
    return model


def upscale_pil_tiled(
    im: Image.Image, model, device: str, tile_size: int = 512, overlap: int = 32
) -> Image.Image:
    """Tile-based 4x super-resolution to avoid memory spikes on large textures."""
    scale = model.scale
    arr = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    h, w, _ = arr.shape
    out_arr = np.zeros((h * scale, w * scale, 3), dtype=np.float32)
    weight_arr = np.zeros((h * scale, w * scale, 1), dtype=np.float32)

    with torch.no_grad():
        for y in range(0, h, tile_size - overlap):
            for x in range(0, w, tile_size - overlap):
                y0 = max(0, min(y, h - tile_size)) if h > tile_size else 0
                x0 = max(0, min(x, w - tile_size)) if w > tile_size else 0
                y1 = min(h, y0 + tile_size)
                x1 = min(w, x0 + tile_size)

                patch = arr[y0:y1, x0:x1]
                ten = torch.from_numpy(patch).permute(2, 0, 1).unsqueeze(0).to(device)
                pred = model(ten).squeeze(0).permute(1, 2, 0).clamp(0.0, 1.0).cpu().numpy()

                oy0, oy1 = y0 * scale, y1 * scale
                ox0, ox1 = x0 * scale, x1 * scale
                out_arr[oy0:oy1, ox0:ox1] += pred
                weight_arr[oy0:oy1, ox0:ox1] += 1.0

                if x1 == w:
                    break
            if y1 == h:
                break

    out_arr = np.clip(out_arr / np.maximum(weight_arr, 1e-6) * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out_arr)


def repack_glb_with_upscaled_textures(
    src_glb: Path, dst_glb: Path, model, device: str, max_dim: int = 4096
) -> tuple[bool, int]:
    """Extract embedded images from GLB, upscale 4x, and repack into dst_glb."""
    data = src_glb.read_bytes()
    magic, version, _ = struct.unpack("<III", data[:12])
    if magic != 0x46546C67 or version != 2:
        raise ValueError(f"Unsupported GLB header: {src_glb}")

    json_len, json_type = struct.unpack("<II", data[12:20])
    gltf = json.loads(data[20 : 20 + json_len].decode("utf-8"))
    imgs = gltf.get("images", [])
    if not imgs:
        dst_glb.parent.mkdir(parents=True, exist_ok=True)
        dst_glb.write_bytes(data)
        return False, 0

    bin_offset = 20 + json_len
    bin_len, bin_type = struct.unpack("<II", data[bin_offset : bin_offset + 8])
    bin_data = data[bin_offset + 8 : bin_offset + 8 + bin_len]

    # Map bufferView indices used by images
    img_bv_indices = {img["bufferView"]: idx for idx, img in enumerate(imgs) if "bufferView" in img}

    new_bin = bytearray()
    for bv_idx, bv in enumerate(gltf.get("bufferViews", [])):
        off = bv.get("byteOffset", 0)
        ln = bv["byteLength"]
        chunk = bin_data[off : off + ln]

        if bv_idx in img_bv_indices:
            img_meta = imgs[img_bv_indices[bv_idx]]
            im = Image.open(io.BytesIO(chunk))
            up = upscale_pil_tiled(im, model, device, tile_size=512, overlap=32)
            if max(up.size) > max_dim:
                up.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            up.save(buf, format="WEBP", quality=90, method=4)
            chunk = buf.getvalue()
            img_meta["mimeType"] = "image/webp"

        # 4-byte align each bufferView
        while len(new_bin) % 4 != 0:
            new_bin.append(0)
        bv["byteOffset"] = len(new_bin)
        bv["byteLength"] = len(chunk)
        new_bin.extend(chunk)

    while len(new_bin) % 4 != 0:
        new_bin.append(0)

    if gltf.get("buffers"):
        gltf["buffers"][0]["byteLength"] = len(new_bin)

    json_bytes = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "

    total_len = 12 + 8 + len(json_bytes) + 8 + len(new_bin)
    out = bytearray()
    out.extend(struct.pack("<III", 0x46546C67, 2, total_len))
    out.extend(struct.pack("<II", len(json_bytes), 0x4E4F534A))
    out.extend(json_bytes)
    out.extend(struct.pack("<II", len(new_bin), 0x004E4942))
    out.extend(new_bin)

    dst_glb.parent.mkdir(parents=True, exist_ok=True)
    dst_glb.write_bytes(bytes(out))
    return True, len(imgs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=Path,
        default=Path.home() / "ComfyUI/models/upscale_models/RealESRGAN_x4plus.pth",
    )
    parser.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    parser.add_argument("--ground-passes", type=int, default=2, help="Number of 4x passes (2 = 16x before cap)")
    parser.add_argument("--max-ground-dim", type=int, default=8192)
    parser.add_argument("--max-building-dim", type=int, default=4096)
    parser.add_argument("--skip-buildings", action="store_true")
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parents[1]
    ground_dir = project_dir / "assets/ground"
    ground_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading upscaler {args.model} on {args.device}...")
    model = load_upscaler(args.model, args.device)

    # 1. Ground GSI seamlessphoto (Scramble Crossing + Center-gai)
    bbox = [139.6968, 35.6588, 139.7016, 35.6615]
    ground_out = ground_dir / "shibuya_ortho_upscaled.png"
    if not ground_out.exists():
        mosaic_path, exact_bbox = fetch_gsi_mosaic(bbox, zoom=18, out_dir=ground_dir)
        im = Image.open(mosaic_path).convert("RGB")
        for p in range(args.ground_passes):
            print(f"Ground upscale pass {p + 1}/{args.ground_passes}: input size={im.size}")
            im = upscale_pil_tiled(im, model, args.device, tile_size=512, overlap=32)
            if max(im.size) > args.max_ground_dim:
                im.thumbnail((args.max_ground_dim, args.max_ground_dim), Image.Resampling.LANCZOS)
        im.save(ground_out)
        (ground_dir / "ground_meta.json").write_text(
            json.dumps({"bbox": exact_bbox, "size": list(im.size)}, indent=2), encoding="utf-8"
        )
        print(f"Saved upscaled ground ({im.size}): {ground_out}")
    else:
        print(f"Using cached upscaled ground: {ground_out}")

    if args.skip_buildings:
        return

    # 2. PLATEAU GLB textures
    src_dir = project_dir / "assets/buildings-shibuya"
    dst_dir = project_dir / "assets/buildings-shibuya-upscaled"
    dst_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((src_dir / "manifest.json").read_text(encoding="utf-8"))

    upscaled_count = 0
    for idx, tile in enumerate(manifest["tiles"]):
        src_glb = src_dir / tile["glb"]
        dst_glb = dst_dir / tile["glb"]
        if dst_glb.exists():
            continue
        changed, img_cnt = repack_glb_with_upscaled_textures(
            src_glb, dst_glb, model, args.device, max_dim=args.max_building_dim
        )
        if changed:
            upscaled_count += 1
        if (idx + 1) % 10 == 0 or (idx + 1) == len(manifest["tiles"]):
            print(f"Processed GLB {idx + 1}/{len(manifest['tiles'])} (textured upscaled: {upscaled_count})")

    (dst_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Finished building texture super-resolution -> {dst_dir}")


if __name__ == "__main__":
    main()
