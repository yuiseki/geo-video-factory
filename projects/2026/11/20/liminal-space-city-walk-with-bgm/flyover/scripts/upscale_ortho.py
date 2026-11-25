#!/usr/bin/env python3
"""GSI seamlessphoto of a box, super-resolved (RealESRGAN_x4plus, BSD-3-Clause), for roofs and ground.

    upscale_ortho.py <out dir> --bbox=w,s,e,n [--zoom=18] [--passes=1] [--model=RealESRGAN_x4plus.pth]
                     [--device=mps|cuda|cpu]

Writes <out dir>/ortho_x{4^passes}.png and ortho_meta.json (the exact tile-aligned bbox and size).
The super-resolved picture is an enlargement for close views: it adds no detail the aerial photo did not
record, and it must be credited as processed from the GSI photo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upscale_shibuya_assets as up  # noqa: E402


def main(argv: list[str]) -> None:
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    out = Path([a for a in argv if not a.startswith("--")][0])
    out.mkdir(parents=True, exist_ok=True)
    bbox = [float(v) for v in opts["bbox"].split(",")]
    zoom, passes = int(opts.get("zoom", 18)), int(opts.get("passes", 1))
    device = opts.get("device") or ("mps" if up.torch.backends.mps.is_available()
                                    else "cuda" if up.torch.cuda.is_available() else "cpu")
    model_path = Path(opts.get("model", Path.home() / "ComfyUI/models/upscale_models/RealESRGAN_x4plus.pth"))
    mosaic, exact = up.fetch_gsi_mosaic(bbox, zoom=zoom, out_dir=out)
    im = up.Image.open(mosaic).convert("RGB")
    model = up.load_upscaler(model_path, device)
    for p in range(passes):
        print(f"pass {p + 1}/{passes}: {im.size} on {device}", flush=True)
        im = up.upscale_pil_tiled(im, model, device, tile_size=512, overlap=32)
    name = f"ortho_x{4 ** passes}.png"
    im.save(out / name)
    (out / "ortho_meta.json").write_text(json.dumps({"image": name, "bbox": exact, "size": list(im.size),
                                                     "zoom": zoom, "passes": passes}, indent=2) + "\n")
    print("wrote", out / name, im.size, exact)


if __name__ == "__main__":
    main(sys.argv[1:])
