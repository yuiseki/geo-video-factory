#!/usr/bin/env python3
"""Experiment: Animate a photorealistic Shibuya keyframe (proto_fp_crossing.png)
for ~3.4 seconds using commercial-friendly Wan 2.2 TI2V 5B (Apache 2.0) via ComfyUI API.
"""
from __future__ import annotations

import argparse
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


def build_wan22_i2v_workflow(
    image_name: str,
    positive: str,
    negative: str,
    width: int = 832,
    height: int = 480,
    length: int = 81,
    steps: int = 20,
    cfg: float = 5.0,
    seed: int = 42,
) -> dict:
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "wan2.2_ti2v_5B_fp16.safetensors",
                "weight_dtype": "default",
            },
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "wan2.2_vae.safetensors"},
        },
        "4": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["1", 0], "shift": 8.0},
        },
        "5": {
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": ["2", 0]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["2", 0]},
        },
        "8": {
            "class_type": "Wan22ImageToVideoLatent",
            "inputs": {
                "vae": ["3", 0],
                "width": width,
                "height": height,
                "length": length,
                "batch_size": 1,
                "start_image": ["5", 0],
            },
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["8", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "uni_pc",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["3", 0]},
        },
        "11": {
            "class_type": "SaveImage",
            "inputs": {"images": ["10", 0], "filename_prefix": "wan22_shibuya_i2v"},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8188")
    parser.add_argument("--width", type=int, default=832)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--length", type=int, default=81)
    parser.add_argument("--steps", type=int, default=20)
    args = parser.parse_args()

    flyover_dir = Path(__file__).resolve().parents[1]
    start_img = flyover_dir / "out/prototype_refs/proto_fp_crossing.png"
    out_frames_dir = flyover_dir / "out/wan22_i2v_test/frames"
    out_frames_dir.mkdir(parents=True, exist_ok=True)

    uploaded = upload_image(args.url, start_img, "proto_fp_crossing.png")
    wf = build_wan22_i2v_workflow(
        uploaded,
        positive=(
            "First-person handheld walking camera moving slowly forward at human walking speed "
            "across the completely deserted Shibuya Scramble Crossing at 3am midnight toward Center-gai. "
            "No people, no cars, quiet eerie liminal atmosphere, gentle realistic footsteps sway, "
            "faint neon reflections shimmering on damp asphalt, cinematic photorealistic footage."
        ),
        negative=(
            "people, pedestrians, crowds, cars, vehicles, fast motion, running, flying, drone, "
            "blurry, distorted buildings, warped text, jitter, flicker"
        ),
        width=args.width,
        height=args.height,
        length=args.length,
        steps=args.steps,
        cfg=5.0,
        seed=42,
    )

    client_id = uuid.uuid4().hex
    body = json.dumps({"prompt": wf, "client_id": client_id}).encode("utf-8")
    res = json.loads(
        api_request(args.url, "/prompt", data=body, headers={"Content-Type": "application/json"})
    )
    prompt_id = res["prompt_id"]
    print(f"Submitted Wan 2.2 TI2V 5B job: {prompt_id}")

    while True:
        hist = json.loads(api_request(args.url, f"/history/{prompt_id}"))
        if prompt_id in hist:
            entry = hist[prompt_id]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI execution failed: {status.get('messages')}")
            outputs = entry.get("outputs", {})
            saved = 0
            for node_out in outputs.values():
                for idx, img_info in enumerate(node_out.get("images", [])):
                    q = urllib.parse.urlencode(
                        {
                            "filename": img_info["filename"],
                            "subfolder": img_info["subfolder"],
                            "type": img_info["type"],
                        }
                    )
                    raw = api_request(args.url, f"/view?{q}")
                    Image.open(io.BytesIO(raw)).save(out_frames_dir / f"frame_{idx:04d}.png")
                    saved += 1
            print(f"Saved {saved} frames to {out_frames_dir}")
            return
        time.sleep(3.0)


if __name__ == "__main__":
    main()
