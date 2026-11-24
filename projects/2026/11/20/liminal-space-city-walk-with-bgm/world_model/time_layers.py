"""time_layers.py <cams.json> <out_dir> [--scene=tris.npz] [--day=0.42] [--night=0.22]

Split posed photos into time layers by how bright the sky is: day, dusk,
night. With --scene the sky is the pixels where the posed camera sees no
geometry; without it, the top quarter of the frame, which fails at a crossing
whose lit signs fill the top of a night photo. A photo with almost no sky
(looking down from a tower) falls back to the brightness of the whole frame. Writes cams_<layer>.json
and layers.json (the measured brightness per photo, so the split can be
checked and corrected by hand). Era is a further axis this does not cover.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def sky_brightness(image):
    """Median luminance (0..1) of the top quarter of an RGB uint8 image."""
    top = np.asarray(image, dtype=np.float32)[: max(1, image.shape[0] // 4)]
    return float(np.median(top @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)) / 255.0)


def masked_brightness(image, mask, least=0.01):
    """Median luminance (0..1) of the masked pixels; the whole frame when under `least` of it is masked."""
    lum = np.asarray(image, dtype=np.float32) @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return float(np.median(lum[mask] if mask.mean() >= least else lum) / 255.0)


def layer_of(brightness, day=0.42, night=0.22):
    return "day" if brightness >= day else "night" if brightness < night else "dusk"


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    cams_path, out = [a for a in argv if not a.startswith("--")]
    cams = json.loads(Path(cams_path).read_text())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    layers, measured = {}, {}
    tris = np.load(opts["scene"])["tris"].astype(np.float64) if "scene" in opts else None
    for key, cam in sorted(cams.items()):
        with Image.open(cam["photo"]) as im:
            if tris is None:
                im.draft("RGB", (640, 640))
                b = sky_brightness(np.asarray(im.convert("RGB")))
            else:
                import surface_atlas as sa
                sky = ~np.isfinite(sa.depth_buffer(tris, cam, scale=480 / cam["width"]))
                sky[sky.shape[0] * 2 // 3:] = False   # below the horizon "no geometry" is the ground
                b = masked_brightness(np.asarray(im.convert("RGB").resize(sky.shape[::-1])), sky)
        name = layer_of(b, float(opts.get("day", 0.42)), float(opts.get("night", 0.22)))
        layers.setdefault(name, {})[key] = cam
        measured[key] = {"sky": round(b, 3), "layer": name}
    for name, part in layers.items():
        (out / f"cams_{name}.json").write_text(json.dumps(part))
        print(name, len(part))
    (out / "layers.json").write_text(json.dumps(measured, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
