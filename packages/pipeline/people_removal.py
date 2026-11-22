"""Remove people and vehicles from a real photo, keeping signs and screens untouched.

Two stages, each run in the environment that has its model:

1. mask (any Python with numpy, Pillow, scipy; a running ComfyUI with SAM 3.1):
   three SAM 3.1 text-prompted passes on one image - people, signs/screens, vehicles.
   final = (people - dilated signs) | fill_holes(vehicles), then grown and softened so motion-blur
   trails past the detected outline are covered too.
   - Signs are subtracted from people because billboards and screens often show people.
   - Vehicles are never protected by signs: a wrapped car can be read as a screen.
   - "poster" and "signboard" are kept out of the sign prompt; they matched car wraps.
2. fill (ComfyUI's venv: torch + spandrel): LaMa (big-lama.pt) at up to MAX_SIDE (1024) px, fully
   convolutional, then composited back into the full-size photo through the soft mask so untouched
   pixels stay original. LaMa does not invent objects; large holes come out smooth and soft.
   (The comfyui-inpaint-nodes LaMa node resizes to 256 px, which is why it is bypassed.)

CLI:
  people_removal.py mask <photo> <out_dir> [--url=http://127.0.0.1:8188] [--threshold=0.2]
      -> <id>_people.png, <id>_signs.png, <id>_vehicles.png (raw SAM layers), <id>_mask.png, <id>_mask_grown.png
  people_removal.py remix <out_dir> <id> ... [--add=<additions.json>] [--folder=<photo folder>]
      rebuild the masks from the saved layers after a rule change; additions.json adds hand-drawn boxes
      for what detection missed: {"<id>": [[x0, y0, x1, y1], ...]} in fractions of the photo
  people_removal.py fill <big-lama.pt> <out_dir> <photo> <mask_grown> [...] [--max-side=1024] [--suffix=_nopeople]
      -> <photo stem>_nopeople.png
<id> is the first three characters of the photo's stem.
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

URL = "http://127.0.0.1:8188"
PEOPLE_PROMPT = "person:300, crowd:20"  # "label:N" sets SAM3_Detect's max detections for that label
SIGN_PROMPT = "billboard:60, screen:40"
VEHICLE_PROMPT = "car:30, taxi:10, bus:5, truck:5"
SAM_MODEL = "sam3.1_multiplex_fp16.safetensors"
OUTPUT_NODES = {"people": "14", "signs": "24", "vehicles": "34"}
MAX_SIDE = 1024  # compared 512-2048 on two night photos: larger repeats stripes, smaller brings back blobs
GROW_FRACTION = 0.012  # of the photo's longer side
# Largest image SAM 3.1 has handled on the 11/22-23 runs (3840x2560); a 3840x5760 photo ran the GPU (MPS) out of memory.
SAM_MAX_PIXELS = 3840 * 2560


def sam_workflow(image_name: str, people=PEOPLE_PROMPT, signs=SIGN_PROMPT, vehicles=VEHICLE_PROMPT,
                 threshold=0.2, sign_threshold=0.25) -> dict:
    """ComfyUI API workflow: one SAM 3.1 model, three prompted detections saved as mask images."""
    wf = {
        "2": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "10": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": SAM_MODEL}},
    }
    for base, text, thr, prefix in ((11, people, threshold, "people_mask"), (21, signs, sign_threshold, "sign_mask"),
                                    (31, vehicles, threshold, "vehicle_mask")):
        b = str(base)
        wf[b] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["10", 1], "text": text}}
        wf[str(base + 1)] = {"class_type": "SAM3_Detect", "inputs": {
            "model": ["10", 0], "image": ["2", 0], "threshold": thr, "refine_iterations": 2,
            "individual_masks": False, "conditioning": [b, 0]}}
        wf[str(base + 2)] = {"class_type": "MaskToImage", "inputs": {"mask": [str(base + 1), 0]}}
        wf[str(base + 3)] = {"class_type": "SaveImage", "inputs": {"images": [str(base + 2), 0], "filename_prefix": prefix}}
    return wf


def combine_masks(people: np.ndarray, signs: np.ndarray, vehicles: np.ndarray, sign_margin: int = 9,
                  max_sign_overlap: float = 0.7, min_vehicle_bottom: float = 0.4, min_vehicle_top: float = 0.1,
                  max_person_sign_overlap: float = 0.5) -> np.ndarray:
    """(people - signs dilated by sign_margin) | real vehicles with holes filled, as a 0/255 uint8 array.

    False detections seen on night street photos, and the rule that drops each:
    - sign art read as a person: a person region at least `max_person_sign_overlap` on (dilated) signs
      is dropped whole, so its fringe outside the sign does not stay in the mask.
    - a curved billboard read as the side of a bus: a vehicle region at least `max_sign_overlap` sign.
    - strips of light near the roofline: a vehicle region ending above `min_vehicle_bottom` of the height.
    - a tower seen from below read as the front of a bus: a vehicle region reaching above `min_vehicle_top`.
      The same tower's lower part is often also read as a crowd: a person region at least
      `max_person_sign_overlap` on such a tower is dropped. (Reaching the top alone does not drop a person:
      passers-by close to the camera and pedestrians in aerial shots do.)
    """
    from scipy import ndimage

    sign = signs > 127
    keep = np.asarray(Image.fromarray((sign * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(sign_margin))) > 0
    out = np.zeros(people.shape, bool)
    h = people.shape[0]
    towers = np.zeros(people.shape, bool)  # vehicle regions reaching the sky: buildings
    veh = ndimage.binary_fill_holes(vehicles > 127)
    labels, _ = ndimage.label(veh)
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        part = labels[sl] == i
        if sl[0].start < min_vehicle_top * h:
            towers[sl] |= part
            continue
        if sign[sl][part].mean() >= max_sign_overlap or sl[0].stop <= min_vehicle_bottom * h:
            continue
        out[sl] |= part
    labels, _ = ndimage.label(people > 127)
    for i, sl in enumerate(ndimage.find_objects(labels), start=1):
        part = labels[sl] == i
        if keep[sl][part].mean() < max_person_sign_overlap and towers[sl][part].mean() < max_person_sign_overlap:
            out[sl] |= part & ~keep[sl]
    return (out * 255).astype(np.uint8)


def add_boxes(mask: np.ndarray, boxes) -> np.ndarray:
    """Mask with hand-drawn boxes [x0, y0, x1, y1] (fractions of the photo) added: for what detection missed."""
    out = mask.copy()
    h, w = out.shape
    for x0, y0, x1, y1 in boxes:
        c0, c1 = max(0, int(x0 * w)), min(w, max(int(x0 * w) + 1, int(np.ceil(x1 * w))))
        r0, r1 = max(0, int(y0 * h)), min(h, max(int(y0 * h) + 1, int(np.ceil(y1 * h))))
        out[r0:r1, c0:c1] = 255
    return out


def boxes_for(additions, stem: str, folder: str = None) -> list:
    """The boxes listed for photo `stem` in an additions file {"<id>": [[x0, y0, x1, y1], ...], ...}.
    Ids repeat across photo folders, so a "<photo folder>/<id>" key wins over the bare id."""
    additions = additions or {}
    if folder and f"{folder}/{stem}" in additions:
        return list(additions[f"{folder}/{stem}"])
    return list(additions.get(stem) or [])


def grow_size(size) -> int:
    return max(3, int(GROW_FRACTION * max(size))) | 1


def grow_mask(mask: Image.Image) -> Image.Image:
    """Dilate then blur: covers motion-blur trails and gives a soft edge for compositing."""
    g = grow_size(mask.size)
    return mask.convert("L").filter(ImageFilter.MaxFilter(g)).filter(ImageFilter.GaussianBlur(g / 3))


def model_size(size, max_side: int = MAX_SIDE):
    w, h = size
    s = min(1.0, max_side / max(w, h))
    return int(w * s) // 8 * 8, int(h * s) // 8 * 8


def sam_size(size, max_pixels: int = None):
    """Size to send to SAM 3.1: the photo's own size, or shrunk (same shape) to max_pixels.
    The masks come back at this size and are resized to the photo."""
    max_pixels = max_pixels or SAM_MAX_PIXELS
    w, h = size
    if w * h <= max_pixels:
        return w, h
    s = (max_pixels / (w * h)) ** 0.5
    return int(w * s), int(h * s)


def composite(photo: Image.Image, fill: Image.Image, soft_mask: Image.Image) -> Image.Image:
    """Fill (any size) inside the soft mask, the untouched photo outside."""
    fill = fill.convert("RGB").resize(photo.size, Image.LANCZOS)
    return Image.composite(fill, photo.convert("RGB"), soft_mask.convert("L").resize(photo.size))


# --- ComfyUI client (network; exercised by the mask command, not by unit tests) ---

def _upload(url: str, img: Image.Image, name: str) -> str:  # pragma: no cover
    buf = io.BytesIO()
    img.save(buf, "PNG")
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            "Content-Type: image/png\r\n\r\n").encode() + buf.getvalue() + \
        f"\r\n--{b}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(url + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    return json.load(urllib.request.urlopen(req))["name"]


def _run(url: str, wf: dict) -> dict:  # pragma: no cover
    req = urllib.request.Request(url + "/prompt", data=json.dumps({"prompt": wf}).encode(),
                                 headers={"Content-Type": "application/json"})
    pid = json.load(urllib.request.urlopen(req))["prompt_id"]
    while True:
        hist = json.load(urllib.request.urlopen(f"{url}/history/{pid}"))
        if pid in hist:
            e = hist[pid]
            if e.get("status", {}).get("status_str") == "error":
                raise RuntimeError(json.dumps(e["status"])[:3000])
            outs = {}
            for node, out in e["outputs"].items():
                for im in out.get("images", []):
                    q = f"filename={im['filename']}&subfolder={im['subfolder']}&type={im['type']}"
                    outs[node] = Image.open(io.BytesIO(urllib.request.urlopen(f"{url}/view?{q}").read()))
            return outs
        time.sleep(1)


def make_mask(photo_path: Path, out_dir: Path, url=URL, threshold=0.2) -> Path:  # pragma: no cover
    photo = Image.open(photo_path).convert("RGB")
    sent = photo.resize(sam_size(photo.size), Image.LANCZOS) if sam_size(photo.size) != photo.size else photo
    outs = _run(url, sam_workflow(_upload(url, sent, "people_in.png"), threshold=threshold))
    layers = {k: np.asarray(outs[n].convert("L").resize(photo.size)) for k, n in OUTPUT_NODES.items()}
    stem = photo_path.stem[:3]
    for k, a in layers.items():
        Image.fromarray(a).save(out_dir / f"{stem}_{k}.png")
    return remix(out_dir, stem)


def remix(out_dir: Path, stem: str, additions=None, folder: str = None) -> Path:  # pragma: no cover
    """Rebuild <stem>_mask.png and _mask_grown.png from the saved SAM layers (no detection rerun),
    plus any hand-drawn boxes for this photo in `additions`."""
    layers = {k: np.asarray(Image.open(out_dir / f"{stem}_{k}.png").convert("L")) for k in OUTPUT_NODES}
    combined = combine_masks(layers["people"], layers["signs"], layers["vehicles"])
    mask = Image.fromarray(add_boxes(combined, boxes_for(additions, stem, folder)))
    mask.save(out_dir / f"{stem}_mask.png")
    print(stem, "mask coverage", round(float((np.asarray(mask) > 127).mean()), 3), flush=True)
    grown = out_dir / f"{stem}_mask_grown.png"
    grow_mask(mask).save(grown)
    return grown


def lama_fill(model_path: str, out_dir: Path, pairs, max_side: int = MAX_SIDE, suffix: str = "_nopeople") -> None:  # pragma: no cover
    import torch
    from spandrel import ModelLoader

    dev = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    model = ModelLoader().load_from_file(model_path).eval().to(dev)
    for photo_path, mask_path in pairs:
        photo = Image.open(photo_path).convert("RGB")
        soft = Image.open(mask_path).convert("L").resize(photo.size)
        w, h = model_size(photo.size, max_side)
        img = torch.from_numpy(np.asarray(photo.resize((w, h), Image.LANCZOS), np.float32) / 255).permute(2, 0, 1)[None]
        m = torch.from_numpy((np.asarray(soft.resize((w, h), Image.BILINEAR)) > 20).astype(np.float32))[None, None]
        with torch.no_grad():
            res = model(img.to(dev), m.to(dev)).clamp(0, 1).cpu()
        fill = Image.fromarray((res[0].permute(1, 2, 0).numpy() * 255).round().astype(np.uint8))
        composite(photo, fill, soft).save(out_dir / f"{Path(photo_path).stem}{suffix}.png")
        print(Path(photo_path).stem[:3], "filled", flush=True)


def main(argv) -> None:  # pragma: no cover
    opts = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in argv if a.startswith("--") and "=" in a}
    args = [a for a in argv if not a.startswith("--")]
    cmd = args[0]
    if cmd == "mask":
        out_dir = Path(args[2])
        out_dir.mkdir(parents=True, exist_ok=True)
        make_mask(Path(args[1]), out_dir, opts.get("--url", URL), float(opts.get("--threshold", 0.2)))
    elif cmd == "remix":
        additions = json.loads(Path(opts["--add"]).read_text()) if "--add" in opts else None
        for stem in args[2:]:
            remix(Path(args[1]), stem, additions, opts.get("--folder"))
    elif cmd == "fill":
        out_dir = Path(args[2])
        out_dir.mkdir(parents=True, exist_ok=True)
        rest = args[3:]
        lama_fill(args[1], out_dir, list(zip(rest[0::2], rest[1::2])), int(opts.get("--max-side", MAX_SIDE)),
                  opts.get("--suffix", "_nopeople"))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
