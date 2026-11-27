"""python -m world_model.tree_mask --photo=<photo> --out=<dir> [--model=openmmlab/upernet-convnext-small]
The trees of a photo as a mask: <out>/tree.png (white where a tree, a plant or a palm stands, at the width the
model worked at), the sky the same way (<out>/sky.png) and <out>/tree.json with the share of each. PLATEAU holds no trees, so where a crown stands against the sky the photo's
skyline is not a roofline; geo/photo_place reads this mask as its veil. The sky mask is for the photos whose sky a
colour reading misses (pale sky behind branches); it is coarser at the roofline than colour.

The model is a semantic segmentation trained on ADE20K (UperNet on ConvNeXt, MIT), not a detector: a detector with
boxes (Grounding DINO, then SAM) finds the trees that stand alone and misses the wood behind them, which is the part
that hides the roofs. No sampling, CPU, deterministic kernels: the same photo gives the same mask.

Needs torch and transformers: run it from an environment that has them (camera_truth/README.md)."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
MODEL = "openmmlab/upernet-convnext-small"
VEIL = ("tree", "plant", "palm")       # ADE20K classes that stand before roofs; grass and flowers lie low
WORK_W = 1024


def veil_ids(id2label):
    """The class numbers whose first name is one of VEIL."""
    ids = sorted(int(i) for i, name in id2label.items() if name.split(",")[0].strip() in VEIL)
    if not ids:
        raise ValueError("the model's labels hold no tree")
    return ids


def veil(seg, id2label):
    """The mask (bool) of a class map."""
    return np.isin(seg, veil_ids(id2label))


def sky(seg, id2label):
    return np.isin(seg, [int(i) for i, name in id2label.items() if name.split(",")[0].strip() == "sky"])


def segment(photo_path, model=MODEL, work_w=WORK_W):
    """(class map at work_w across, id2label)."""
    import torch
    from transformers import AutoImageProcessor, UperNetForSemanticSegmentation
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(0)
    proc = AutoImageProcessor.from_pretrained(model)
    net = UperNetForSemanticSegmentation.from_pretrained(model).eval()
    with Image.open(photo_path) as opened:
        w, h = opened.size
        img = opened.convert("RGB").resize((work_w, round(work_w * h / w)), Image.LANCZOS)
    with torch.no_grad():
        logits = net(**proc(images=img, return_tensors="pt")).logits
    seg = torch.nn.functional.interpolate(logits, size=img.size[::-1], mode="bilinear", align_corners=False)
    return seg[0].argmax(0).numpy(), net.config.id2label


def main(argv):
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in argv if a.startswith("--"))
    if "photo" not in opts or "out" not in opts:
        raise SystemExit(__doc__)
    model = opts.get("model", MODEL)
    seg, labels = segment(opts["photo"], model)
    mask, above = veil(seg, labels), sky(seg, labels)
    out = Path(opts["out"]); out.mkdir(parents=True, exist_ok=True)
    Image.fromarray((mask * 255).astype(np.uint8)).convert("1").save(out / "tree.png", optimize=True)
    Image.fromarray((above * 255).astype(np.uint8)).convert("1").save(out / "sky.png", optimize=True)
    (out / "tree.json").write_text(json.dumps({"model": model, "share": round(float(mask.mean()), 4),
                                               "sky": round(float(above.mean()), 4)}))


if __name__ == "__main__":
    main(sys.argv[1:])
