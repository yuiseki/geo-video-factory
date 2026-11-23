#!/usr/bin/env python3
"""Refine Shibuya ground ortho and PLATEAU GLB textures via ComfyUI API
using commercial-licensed SDXL Base 1.0 + xinsir ControlNet Tile + sdxl-vae-fp16-fix,
followed by RealESRGAN_x4plus super-resolution.
"""
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path
import struct
import time
import urllib.parse
import urllib.request
import uuid

from PIL import Image, ImageEnhance


def api_request(base_url: str, path: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers or {},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def upload_image(base_url: str, img_path: Path, name: str) -> str:
    boundary = uuid.uuid4().hex
    payload = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + img_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    res = json.loads(api_request(base_url, "/upload/image", data=payload, headers=headers))
    return res["name"]


def build_sdxl_tile_workflow(
    image_name: str,
    positive: str,
    negative: str,
    denoise: float = 0.55,
    cn_strength: float = 0.85,
    steps: int = 24,
    cfg: float = 6.5,
    seed: int = 42,
) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        },
        "2": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "sdxl_vae_fp16_fix.safetensors"},
        },
        "3": {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": "xinsir-controlnet-tile-sdxl-1.0.safetensors"},
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": ["1", 1]},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["1", 1]},
        },
        "7": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["5", 0],
                "negative": ["6", 0],
                "control_net": ["3", 0],
                "image": ["4", 0],
                "strength": cn_strength,
                "start_percent": 0.0,
                "end_percent": 0.9,
                "vae": ["2", 0],
            },
        },
        "8": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["4", 0], "vae": ["2", 0]},
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["7", 0],
                "negative": ["7", 1],
                "latent_image": ["8", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": denoise,
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["2", 0]},
        },
        "11": {
            "class_type": "SaveImage",
            "inputs": {"images": ["10", 0], "filename_prefix": "shibuya_refine"},
        },
    }


def run_workflow(base_url: str, workflow: dict) -> Image.Image:
    client_id = uuid.uuid4().hex
    body = json.dumps({"prompt": workflow, "client_id": client_id}).encode("utf-8")
    res = json.loads(
        api_request(base_url, "/prompt", data=body, headers={"Content-Type": "application/json"})
    )
    prompt_id = res["prompt_id"]

    while True:
        hist = json.loads(api_request(base_url, f"/history/{prompt_id}"))
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI execution failed: {status.get('messages')}")
            outputs = entry.get("outputs", {})
            for node_out in outputs.values():
                if "images" in node_out:
                    img_info = node_out["images"][0]
                    q = urllib.parse.urlencode(
                        {
                            "filename": img_info["filename"],
                            "subfolder": img_info["subfolder"],
                            "type": img_info["type"],
                        }
                    )
                    raw = api_request(base_url, f"/view?{q}")
                    return Image.open(io.BytesIO(raw)).convert("RGB")
            raise RuntimeError(f"ComfyUI finished without image outputs: {entry}")
        time.sleep(1.0)


def dist_sq(region: list[float], target_lon: float, target_lat: float) -> float:
    # region in radians [west, south, east, north, ...]
    lon = math.degrees((region[0] + region[2]) * 0.5)
    lat = math.degrees((region[1] + region[3]) * 0.5)
    return (lon - target_lon) ** 2 + (lat - target_lat) ** 2


def refine_ground(base_url: str, project_dir: Path) -> None:
    ground_dir = project_dir / "assets/ground"
    src_path = ground_dir / "shibuya_ortho_z18.png"
    work_path = ground_dir / "shibuya_ortho_sdxl_in.png"
    # Pre-darken daytime ortho so SDXL img2img naturally renders midnight wet asphalt
    im = Image.open(src_path).convert("RGB").resize((1280, 960), Image.Resampling.LANCZOS)
    im = ImageEnhance.Brightness(im).enhance(0.32)
    im = ImageEnhance.Contrast(im).enhance(1.25)
    im.save(work_path)

    uploaded = upload_image(base_url, work_path, "shibuya_ground_in.png")
    wf = build_sdxl_tile_workflow(
        uploaded,
        positive=(
            "top-down aerial orthophoto of deserted Tokyo Shibuya Scramble Crossing at 3am midnight, "
            "dark wet black asphalt road, crisp sharp white crosswalk stripes, faint cyan and purple neon reflections on wet pavement, "
            "completely empty streets, zero cars, zero people, photorealistic ultra sharp texture"
        ),
        negative=(
            "cars, vehicles, buses, taxis, pedestrians, people, crowds, daytime sunlight, bright white roofs, "
            "blurry, lowres, jpeg artifacts, watermark, text"
        ),
        denoise=0.66,
        cn_strength=0.82,
        steps=24,
        cfg=6.8,
        seed=102,
    )
    print("Running SDXL + ControlNet Tile on pre-darkened Shibuya ground ortho...")
    refined = run_workflow(base_url, wf)
    out_sdxl = ground_dir / "shibuya_ortho_sdxl.png"
    refined.save(out_sdxl)
    print(f"Saved SDXL ground: {out_sdxl} ({refined.size})")


def refine_top_buildings(base_url: str, project_dir: Path, top_n: int = 8) -> None:
    src_dir = project_dir / "assets/buildings-shibuya"
    dst_dir = project_dir / "assets/buildings-shibuya-sdxl"
    dst_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = project_dir / "out/sdxl_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((src_dir / "manifest.json").read_text(encoding="utf-8"))
    # Sort tiles closest to Scramble Crossing / Center-gai entrance
    target_lon, target_lat = 139.7002, 35.6598
    textured = []
    for t in manifest["tiles"]:
        reg = t.get("region")
        if not reg:
            continue
        p = src_dir / t["glb"]
        d = p.read_bytes()
        jl = struct.unpack("<I", d[12:16])[0]
        g = json.loads(d[20 : 20 + jl].decode("utf-8"))
        if g.get("images"):
            textured.append(t)
    textured.sort(key=lambda t: dist_sq(t["region"], target_lon, target_lat))
    chosen_glbs = {t["glb"] for t in textured[:top_n]}
    print(f"Selected {len(chosen_glbs)} nearest textured GLB tiles for SDXL refinement.")

    # Copy non-chosen GLBs from upscaled set if available, else original
    upscaled_dir = project_dir / "assets/buildings-shibuya-upscaled"

    for idx, tile in enumerate(manifest["tiles"]):
        glb_rel = tile["glb"]
        dst_glb = dst_dir / glb_rel
        dst_glb.parent.mkdir(parents=True, exist_ok=True)
        if glb_rel not in chosen_glbs:
            fallback = upscaled_dir / glb_rel if (upscaled_dir / glb_rel).exists() else src_dir / glb_rel
            dst_glb.write_bytes(fallback.read_bytes())
            continue

        src_glb = src_dir / glb_rel
        data = src_glb.read_bytes()
        json_len = struct.unpack("<I", data[12:16])[0]
        gltf = json.loads(data[20 : 20 + json_len].decode("utf-8"))
        imgs = gltf.get("images", [])
        if not imgs:
            dst_glb.write_bytes(data)
            continue

        bin_offset = 20 + json_len
        bin_len = struct.unpack("<I", data[bin_offset : bin_offset + 4])[0]
        bin_data = data[bin_offset + 8 : bin_offset + 8 + bin_len]
        img_bv_indices = {img["bufferView"]: i for i, img in enumerate(imgs) if "bufferView" in img}

        new_bin = bytearray()
        for bv_idx, bv in enumerate(gltf.get("bufferViews", [])):
            off = bv.get("byteOffset", 0)
            ln = bv["byteLength"]
            chunk = bin_data[off : off + ln]

            if bv_idx in img_bv_indices:
                img_meta = imgs[img_bv_indices[bv_idx]]
                im = Image.open(io.BytesIO(chunk)).convert("RGB")
                orig_size = im.size
                # Cap input to 1024px max side so MPS attention stays well under INT_MAX
                sdxl_in = im.copy()
                if max(sdxl_in.size) > 1024:
                    sdxl_in.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                # Ensure multiples of 64 for SDXL
                w64 = max(64, (sdxl_in.width // 64) * 64)
                h64 = max(64, (sdxl_in.height // 64) * 64)
                if (w64, h64) != sdxl_in.size:
                    sdxl_in = sdxl_in.resize((w64, h64), Image.Resampling.LANCZOS)
                in_path = tmp_dir / f"{src_glb.stem}_{bv_idx}.png"
                ImageEnhance.Brightness(sdxl_in).enhance(0.55).save(in_path)
                uploaded = upload_image(base_url, in_path, in_path.name)
                wf = build_sdxl_tile_workflow(
                    uploaded,
                    positive=(
                        "photorealistic Tokyo Shibuya commercial building facade texture atlas at 3am night, "
                        "crisp glass curtain walls, realistic concrete tiles, glowing neon Japanese signs, "
                        "closed ground floor metal shutters, sharp architectural texture, high detail"
                    ),
                    negative="blurry, lowres, jpeg artifacts, people, pedestrians, distortion",
                    denoise=0.42,
                    cn_strength=0.90,
                    steps=20,
                    cfg=6.0,
                    seed=200 + idx,
                )
                print(f"Refining building GLB {src_glb.name} texture ({orig_size}) via SDXL...")
                refined = run_workflow(base_url, wf)
                target_size = (min(2048, orig_size[0] * 2), min(2048, orig_size[1] * 2))
                refined = refined.resize(target_size, Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                refined.save(buf, format="WEBP", quality=90, method=4)
                chunk = buf.getvalue()
                img_meta["mimeType"] = "image/webp"

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

        out = bytearray()
        total_len = 12 + 8 + len(json_bytes) + 8 + len(new_bin)
        out.extend(struct.pack("<III", 0x46546C67, 2, total_len))
        out.extend(struct.pack("<II", len(json_bytes), 0x4E4F534A))
        out.extend(json_bytes)
        out.extend(struct.pack("<II", len(new_bin), 0x004E4942))
        out.extend(new_bin)
        dst_glb.write_bytes(bytes(out))

    (dst_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Finished SDXL building texture refinement -> {dst_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--top-buildings", type=int, default=8)
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parents[1]
    refine_ground(args.url, project_dir)
    refine_top_buildings(args.url, project_dir, top_n=args.top_buildings)


if __name__ == "__main__":
    main()
