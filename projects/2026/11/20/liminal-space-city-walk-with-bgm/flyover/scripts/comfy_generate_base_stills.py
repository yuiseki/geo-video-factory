#!/usr/bin/env python3
"""Reproducibly generate photorealistic deserted midnight base stills
solely via local ComfyUI (SDXL Base 1.0 + xinsir ControlNet Tile + fixed seed + euler).
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

from PIL import Image


def api_request(base_url: str, path: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=120) as resp:
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


def build_deterministic_sdxl_workflow(
    image_name: str,
    positive: str,
    negative: str,
    denoise: float,
    cn_strength: float,
    seed: int,
    steps: int = 28,
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
                "end_percent": 0.80,
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
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": denoise,
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["2", 0]},
        },
        "11": {
            "class_type": "SaveImage",
            "inputs": {"images": ["10", 0], "filename_prefix": "comfy_base_still"},
        },
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


def generate_one(
    base_url: str,
    src_path: Path,
    out_path: Path,
    positive: str,
    negative: str,
    denoise: float,
    cn_strength: float,
    seed: int,
) -> None:
    tmp_in = out_path.parent / f"_in_{out_path.name}"
    # 1216x704 is a 64-aligned 16:9-ish resolution ideal for SDXL on MPS
    im = Image.open(src_path).convert("RGB").resize((1216, 704), Image.Resampling.LANCZOS)
    im.save(tmp_in)

    uploaded = upload_image(base_url, tmp_in, tmp_in.name)
    wf = build_deterministic_sdxl_workflow(
        uploaded,
        positive=positive,
        negative=negative,
        denoise=denoise,
        cn_strength=cn_strength,
        seed=seed,
    )
    print(f"Generating {out_path.name} via ComfyUI (seed={seed}, denoise={denoise}, cn={cn_strength})...")
    result = run_workflow(base_url, wf)
    result = result.resize((1280, 720), Image.Resampling.LANCZOS)
    result.save(out_path)
    tmp_in.unlink(missing_ok=True)
    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()[:12]
    print(f"Saved {out_path} (sha256={sha})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    flyover_dir = Path(__file__).resolve().parents[1]
    refs_dir = flyover_dir / "out/prototype_refs"
    out_dir = flyover_dir / "out/comfy_repro"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. First-person Shibuya Crossing
    generate_one(
        args.url,
        refs_dir / "v11_crossing_layout.png",
        out_dir / "comfy_fp_crossing.png",
        positive=(
            "photorealistic photograph of deserted Tokyo Shibuya Scramble Crossing at 3am midnight, "
            "human eye-level perspective, crisp white crosswalk stripes on dark wet asphalt reflecting "
            "cyan and purple neon lights, glowing Japanese commercial building signs and glass curtain walls, "
            "completely empty streets, zero people, zero cars, eerie liminal space atmosphere, ultra detailed, 8k"
        ),
        negative=(
            "people, pedestrians, crowds, cars, vehicles, daytime, sunlight, blurry, lowres, "
            "cartoon, anime, painting, watermark, deformed"
        ),
        denoise=0.72,
        cn_strength=0.72,
        seed=20261121,
    )

    # 2. Elevated CCTV CAM-02
    generate_one(
        args.url,
        refs_dir / "cctv_cam02_layout.png",
        out_dir / "comfy_cctv_cam02.png",
        positive=(
            "photorealistic elevated surveillance camera view of deserted Tokyo Shibuya Scramble Crossing "
            "and JR Shibuya Station at 3am midnight, dark wet asphalt with crisp white crosswalks, "
            "glowing train station platform lights, traffic signals, subtle neon reflections, "
            "completely empty city, zero people, zero cars, cinematic night photography, sharp details"
        ),
        negative=(
            "people, pedestrians, crowds, cars, buses, taxis, daytime, blurry, lowres, "
            "cartoon, painting, watermark, text overlay"
        ),
        denoise=0.74,
        cn_strength=0.70,
        seed=20261122,
    )


if __name__ == "__main__":
    main()
