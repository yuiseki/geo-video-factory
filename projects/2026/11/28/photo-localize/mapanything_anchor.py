"""Every photo of a set placed in the city model's frame, from one photo geo.photo_solve placed (MapAnything).

    python mapanything_anchor.py <photo dir> <anchor photo name> <anchor solve.json> <out.json> [--no-anchor]

The anchor goes first with its pose (cam2world: Rw transposed, eye) and its intrinsics; every other photo goes with
the intrinsics its EXIF 35 mm focal length gives (none when the EXIF has none). MapAnything (the Apache-2.0
weights, facebook/map-anything-apache) returns every camera in the anchor's metric frame, which is the frame of
the anchor's solve.json (metres east, north, up from its "origin"). Writes {name: {eye, Rw, params, width,
height}, "origin": ...}. --no-anchor gives no pose to anyone (the model's own frame, for comparison).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

MODEL = "facebook/map-anything-apache"
DIAG_35MM = math.hypot(36, 24)


def photo(path):
    im = ImageOps.exif_transpose(Image.open(path))
    f35 = Image.open(path).getexif().get_ifd(0x8769).get(41989)
    return np.asarray(im.convert("RGB")), (float(f35) if f35 else None)


def k_matrix(fx, fy, cx, cy):
    import torch
    return torch.tensor([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=torch.float32)


def pose_of(cam):
    """photo_solve's camera (x_cam = Rw @ (x - eye), x right, y down, z forward) as OpenCV cam2world 4 x 4."""
    pose = np.eye(4)
    pose[:3, :3] = np.asarray(cam["Rw"], float).T
    pose[:3, 3] = cam["eye"]
    return pose


def camera_of(pose):
    """The inverse of pose_of: eye and Rw from a cam2world 4 x 4."""
    pose = np.asarray(pose, float)
    return {"eye": pose[:3, 3].tolist(), "Rw": pose[:3, :3].T.tolist()}


def main(argv):
    import torch
    from mapanything.models import MapAnything
    from mapanything.utils.image import preprocess_inputs
    photos, anchor, solve_path, out = Path(argv[0]), argv[1], json.load(open(argv[2])), Path(argv[3])
    use_anchor = "--no-anchor" not in argv
    names = [anchor] + sorted(p.name for p in photos.glob("*.jpg") if p.name != anchor)
    views = []
    for name in names:
        img, f35 = photo(photos / name)
        h, w = img.shape[:2]
        v = {"img": torch.from_numpy(img)}
        if name == anchor:
            cam = solve_path["camera"]
            v["intrinsics"] = k_matrix(*cam["params"])
            if use_anchor:
                v["camera_poses"] = torch.tensor(pose_of(cam), dtype=torch.float32)
                v["is_metric_scale"] = torch.tensor([True])
        elif f35:
            f = f35 / DIAG_35MM * math.hypot(w, h)
            v["intrinsics"] = k_matrix(f, f, w / 2, h / 2)
        views.append(v)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    model = MapAnything.from_pretrained(MODEL).to(dev)
    preds = model.infer(preprocess_inputs(views), memory_efficient_inference=True, use_amp=True, amp_dtype="bf16")
    res = {"origin": solve_path["origin"], "anchor": anchor, "anchored": use_anchor}
    for name, p in zip(names, preds):
        pose = p["camera_poses"][0].float().cpu().numpy()
        k = p["intrinsics"][0].float().cpu().numpy()
        hh, ww = p["img_no_norm"].shape[1:3]
        res[name] = {**camera_of(pose),
                     "params": [float(k[0, 0]), float(k[1, 1]), float(k[0, 2]), float(k[1, 2])],
                     "width": int(ww), "height": int(hh)}
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(len(names), "photos placed;", "anchored on" if use_anchor else "no anchor, first is", anchor)


if __name__ == "__main__":
    main(sys.argv[1:])
