#!/usr/bin/env python3
"""Generate photorealistic deserted midnight Shibuya stills reproducibly via local ComfyUI
using SDXL Base 1.0 + ControlNet Union ProMax (Canny) + IP-Adapter Plus (style transfer
from real Shibuya night photos) + fixed seed + euler sampler.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import uuid

import cv2
import numpy as np
from PIL import Image


def api_request(base_url: str, path: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=180) as resp:
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


def make_clean_canny(src_path: Path, out_in_path: Path, out_canny_path: Path) -> None:
    """Mask out bottom-right renderer credit text and extract crisp Canny edges."""
    im = Image.open(src_path).convert("RGB").resize((1216, 704), Image.Resampling.LANCZOS)
    arr = np.asarray(im, dtype=np.uint8).copy()
    # Replace bottom-right credit corner with nearby dark pavement median
    patch = arr[590:630, 820:920]
    med = np.median(patch, axis=(0, 1)).astype(np.uint8)
    arr[625:704, 880:1216] = med
    Image.fromarray(arr).save(out_in_path)

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 35, 110)
    Image.fromarray(edges).convert("RGB").save(out_canny_path)


def build_v2_workflow(
    base_img_name: str,
    canny_img_name: str,
    ref_img_name: str,
    positive: str,
    negative: str,
    seed: int,
    cn_strength: float = 0.68,
    ip_weight: float = 0.58,
    denoise: float = 0.90,
    steps: int = 30,
    cfg: float = 7.0,
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
            "inputs": {"control_net_name": "xinsir-controlnet-union-sdxl-promax.safetensors"},
        },
        "4": {
            "class_type": "SetUnionControlNetType",
            "inputs": {"control_net": ["3", 0], "type": "canny/lineart/anime_lineart/mlsd"},
        },
        "5": {
            "class_type": "IPAdapterModelLoader",
            "inputs": {"ipadapter_file": "ip-adapter-plus_sdxl_vit-h.safetensors"},
        },
        "6": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"},
        },
        "7": {"class_type": "LoadImage", "inputs": {"image": base_img_name}},
        "8": {"class_type": "LoadImage", "inputs": {"image": canny_img_name}},
        "9": {"class_type": "LoadImage", "inputs": {"image": ref_img_name}},
        "10": {
            "class_type": "IPAdapterAdvanced",
            "inputs": {
                "model": ["1", 0],
                "ipadapter": ["5", 0],
                "image": ["9", 0],
                "weight": ip_weight,
                "weight_type": "style transfer",
                "combine_embeds": "concat",
                "start_at": 0.0,
                "end_at": 0.85,
                "embeds_scaling": "V only",
                "clip_vision": ["6", 0],
            },
        },
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
        "12": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "13": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["11", 0],
                "negative": ["12", 0],
                "control_net": ["4", 0],
                "image": ["8", 0],
                "strength": cn_strength,
                "start_percent": 0.0,
                "end_percent": 0.78,
                "vae": ["2", 0],
            },
        },
        "14": {"class_type": "VAEEncode", "inputs": {"pixels": ["7", 0], "vae": ["2", 0]}},
        "15": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["10", 0],
                "positive": ["13", 0],
                "negative": ["13", 1],
                "latent_image": ["14", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": denoise,
            },
        },
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["2", 0]}},
        "17": {"class_type": "SaveImage", "inputs": {"images": ["16", 0], "filename_prefix": "comfy_v2"}},
    }


def run_workflow(base_url: str, wf: dict) -> Image.Image:
    client_id = uuid.uuid4().hex
    body = json.dumps({"prompt": wf, "client_id": client_id}).encode("utf-8")
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
            for node_out in entry.get("outputs", {}).values():
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    flyover_dir = Path(__file__).resolve().parents[1]
    refs_dir = flyover_dir / "out/prototype_refs"
    photos_dir = flyover_dir / "assets/photos"
    out_dir = flyover_dir / "out/comfy_repro_v2"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Prepare clean inputs & Canny edges
    fp_in = out_dir / "_in_fp_crossing.png"
    fp_canny = out_dir / "_canny_fp_crossing.png"
    make_clean_canny(refs_dir / "v11_crossing_layout.png", fp_in, fp_canny)

    cam02_in = out_dir / "_in_cctv_cam02.png"
    cam02_canny = out_dir / "_canny_cctv_cam02.png"
    make_clean_canny(refs_dir / "cctv_cam02_layout.png", cam02_in, cam02_canny)

    # Convert reference photos to clean PNGs for upload
    ref_crossing_png = out_dir / "_ref_crossing.png"
    Image.open(photos_dir / "shibuya_crossing/004_Shibuya_-04.jpg").convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS).save(ref_crossing_png)

    ref_cam02_png = out_dir / "_ref_cam02.png"
    Image.open(photos_dir / "shibuya_crossing/052_Shibuya_Tokyo_Japan_48847062017.jpg").convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS).save(ref_cam02_png)

    # Upload all
    up_fp_in = upload_image(args.url, fp_in, "v2_fp_in.png")
    up_fp_canny = upload_image(args.url, fp_canny, "v2_fp_canny.png")
    up_fp_ref = upload_image(args.url, ref_crossing_png, "v2_fp_ref.png")

    wf1 = build_v2_workflow(
        up_fp_in,
        up_fp_canny,
        up_fp_ref,
        positive=(
            "photorealistic 35mm night photograph of deserted Tokyo Shibuya Scramble Crossing at 3am midnight, "
            "eye-level view, crisp white crosswalk stripes on dark wet asphalt reflecting glowing neon signs, "
            "illuminated Japanese commercial skyscrapers, glass facades, completely empty streets, "
            "zero people, zero cars, eerie liminal space atmosphere, ultra sharp, high contrast"
        ),
        negative=(
            "people, pedestrians, crowds, person, human, cars, buses, taxis, traffic, "
            "daytime, sunlight, blurry, lowres, fog, haze, watermark, text overlay, deformed"
        ),
        seed=20261121,
        cn_strength=0.65,
        ip_weight=0.55,
        denoise=0.92,
    )
    print("Generating comfy_v2_fp_crossing.png (ControlNet Canny + IP-Adapter style transfer)...")
    res1 = run_workflow(args.url, wf1).resize((1280, 720), Image.Resampling.LANCZOS)
    p1 = out_dir / "comfy_v2_fp_crossing.png"
    res1.save(p1)
    print(f"Saved {p1} (sha256={hashlib.sha256(p1.read_bytes()).hexdigest()[:12]})")

    up_c2_in = upload_image(args.url, cam02_in, "v2_c2_in.png")
    up_c2_canny = upload_image(args.url, cam02_canny, "v2_c2_canny.png")
    up_c2_ref = upload_image(args.url, ref_cam02_png, "v2_c2_ref.png")

    wf2 = build_v2_workflow(
        up_c2_in,
        up_c2_canny,
        up_c2_ref,
        positive=(
            "photorealistic elevated night street-cam photograph overlooking deserted Tokyo Shibuya Scramble Crossing "
            "and JR Shibuya Station at 3am midnight, wet dark asphalt with white crosswalks, "
            "bright train station platform lights, subtle cyan and amber reflections, "
            "completely empty streets, zero people, zero cars, sharp architectural details"
        ),
        negative=(
            "people, pedestrians, crowds, cars, buses, taxis, daytime, blurry, lowres, "
            "fog, haze, watermark, text overlay"
        ),
        seed=20261122,
        cn_strength=0.65,
        ip_weight=0.50,
        denoise=0.92,
    )
    print("Generating comfy_v2_cctv_cam02.png (ControlNet Canny + IP-Adapter style transfer)...")
    res2 = run_workflow(args.url, wf2).resize((1280, 720), Image.Resampling.LANCZOS)
    p2 = out_dir / "comfy_v2_cctv_cam02.png"
    res2.save(p2)
    print(f"Saved {p2} (sha256={hashlib.sha256(p2.read_bytes()).hexdigest()[:12]})")


if __name__ == "__main__":
    main()
