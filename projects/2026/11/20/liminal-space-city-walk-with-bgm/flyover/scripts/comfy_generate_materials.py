#!/usr/bin/env python3
"""Generate tileable material textures (wet asphalt, Center-gai brick pavement,
and Tokyo commercial building facades) using local ComfyUI (SDXL Base 1.0 + fixed seed).
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import uuid

import numpy as np
from PIL import Image, ImageDraw


def api_request(base_url: str, path: str, data: bytes | None = None, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def build_txt2img_workflow(positive: str, negative: str, seed: int, width: int = 1024, height: int = 1024) -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        },
        "2": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "sdxl_vae_fp16_fix.safetensors"},
        },
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": 28,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["2", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "comfy_mat"}},
    }


def make_glass_grid_canny(size: int = 1024) -> Image.Image:
    im = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    # 4 storeys high, 4 bays wide -> exact 1024x1024 orthographic grid
    for i in range(5):
        p = int(round(i * size / 4))
        draw.line([(p, 0), (p, size)], fill=(255, 255, 255), width=4)
        draw.line([(0, p), (size, p)], fill=(255, 255, 255), width=6)
    # Sub-mullions
    for i in range(4):
        x0 = int(round(i * size / 4))
        xm = x0 + size // 8
        draw.line([(xm, 0), (xm, size)], fill=(180, 180, 180), width=2)
        ym = x0 + int(size * 0.16)
        draw.line([(0, ym), (size, ym)], fill=(180, 180, 180), width=2)
    return im


def make_shutter_grid_canny(size: int = 1024) -> Image.Image:
    im = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(im)
    # Left/right concrete/tile piers
    draw.rectangle([0, 0, 96, size], outline=(255, 255, 255), width=4)
    draw.rectangle([size - 96, 0, size - 1, size], outline=(255, 255, 255), width=4)
    # Horizontal roll-up shutter slats
    for y in range(24, size, 32):
        draw.line([(96, y), (size - 96, y)], fill=(220, 220, 220), width=2)
    # Center vertical guide rail
    draw.line([(size // 2, 0), (size // 2, size)], fill=(255, 255, 255), width=4)
    return im


def build_controlnet_workflow(
    positive: str,
    negative: str,
    seed: int,
    canny_filename: str,
    strength: float = 0.72,
    width: int = 1024,
    height: int = 1024,
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
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "9": {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": "xinsir-controlnet-union-sdxl-promax.safetensors"},
        },
        "10": {"class_type": "LoadImage", "inputs": {"image": canny_filename}},
        "11": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["3", 0],
                "negative": ["4", 0],
                "control_net": ["9", 0],
                "image": ["10", 0],
                "strength": strength,
                "start_percent": 0.0,
                "end_percent": 0.85,
            },
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["11", 0],
                "negative": ["11", 1],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": 28,
                "cfg": 6.5,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["2", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "comfy_mat"}},
    }


def upload_image(base_url: str, img: Image.Image, filename: str) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    boundary = uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\nContent-Type: image/png\r\n\r\n".encode(),
        buf.getvalue(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    res = json.loads(
        api_request(
            base_url,
            "/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    )
    return res["name"]


def make_seamless_mirror_blend(im: Image.Image) -> Image.Image:
    """Create a 1024x1024 seamlessly tileable texture via half-shift cross-fade."""
    arr = np.asarray(im.convert("RGB"), dtype=np.float32)
    h, w, _ = arr.shape
    shifted = np.roll(np.roll(arr, h // 2, axis=0), w // 2, axis=1)
    y = np.abs(np.linspace(-1.0, 1.0, h, dtype=np.float32))[:, None, None]
    x = np.abs(np.linspace(-1.0, 1.0, w, dtype=np.float32))[None, :, None]
    # Weight = 1 in center of original, 0 at edges (where shifted center lives)
    w_orig = np.clip((1.0 - np.maximum(x, y)) * 2.5, 0.0, 1.0)
    blended = arr * w_orig + shifted * (1.0 - w_orig)
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))


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
            raise RuntimeError(f"No image output: {entry}")
        time.sleep(1.0)


def main() -> None:
    flyover_dir = Path(__file__).resolve().parents[1]
    out_dir = flyover_dir / "assets/materials"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_url = "http://127.0.0.1:8188"

    specs = [
        (
            "mat_wet_asphalt.png",
            4001,
            True,
            "top-down orthographic seamless texture of dark wet black asphalt road surface at night, "
            "fine mineral aggregate grain, subtle damp puddles, uniform flat lighting, no shadows, 8k PBR albedo",
            "perspective, horizon, cars, crosswalk lines, people, text, blurry, strong directional shadow",
        ),
        (
            "mat_centergai_brick.png",
            4012,
            False,
            "top-down orthographic close-up texture filling the entire frame edge-to-edge of dark wet charcoal-slate Japanese interlocking concrete brick pavement at night, "
            "subtle damp sheen, uniform flat lighting, no shadows, 8k PBR albedo",
            "perspective, horizon, people, trash, text, blurry, strong shadow, bright purple, cartoon",
        ),
        (
            "mat_facade_glass.png",
            4013,
            False,
            "close-up flat front texture filling the entire frame edge-to-edge of a modern glass curtain wall grid on a Tokyo office building at night, "
            "repeating dark aluminum mullions and dark reflective glass panes, a few interior office windows dimly lit with cool and warm fluorescent light, "
            "no sky, no building edges, no horizon, orthographic flat pattern",
            "sky, clouds, building silhouette, rooftop, street, ground, perspective, vanishing point, trees, people, text, watermark, blurry",
        ),
        (
            "mat_facade_shutter.png",
            4014,
            False,
            "close-up flat front texture filling the entire frame edge-to-edge of closed corrugated grey steel roll-up security shutters and dark weathered concrete wall panels at night, "
            "dim sodium streetlight sheen on metal slats, no sidewalk, no road, no sky, orthographic flat elevation",
            "open shop, merchandise, food, sidewalk, road, sky, people, bicycles, awning, roof, perspective, vanishing point, text, watermark, blurry",
        ),
    ]

    for fname, seed, make_seamless, pos, neg in specs:
        out_path = out_dir / fname
        if fname in ("mat_wet_asphalt.png", "mat_centergai_brick.png") and out_path.exists():
            print(f"Skipping existing {fname}")
            continue
        print(f"Generating {fname} (seed={seed})...")
        if fname == "mat_facade_glass.png":
            canny_name = upload_image(base_url, make_glass_grid_canny(), "glass_grid_canny.png")
            wf = build_controlnet_workflow(pos, neg, seed=seed, canny_filename=canny_name, strength=0.78)
        elif fname == "mat_facade_shutter.png":
            canny_name = upload_image(base_url, make_shutter_grid_canny(), "shutter_grid_canny.png")
            wf = build_controlnet_workflow(pos, neg, seed=seed, canny_filename=canny_name, strength=0.78)
        else:
            wf = build_txt2img_workflow(pos, neg, seed=seed)
        im = run_workflow(base_url, wf)
        if make_seamless:
            im = make_seamless_mirror_blend(im)
        im.save(out_path)
        sha = hashlib.sha256(out_path.read_bytes()).hexdigest()[:12]
        print(f"Saved {out_path} (sha256={sha})")


if __name__ == "__main__":
    main()
