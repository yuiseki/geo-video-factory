"""One global descriptor per photo, for vpr_eval.py score.

    python describe.py megaloc <items.jsonl> <out.npy>
    python describe.py anyloc <items.jsonl> <out.npy> <AnyLoc clone> <vocabulary dir>

megaloc: MegaLoc as its README evaluates it (ImageNet normalisation, 322 x 322).
anyloc:  AnyLoc-VLAD-DINOv2 as its demo builds it (ViT-G/14, layer 31, value facet,
         32 clusters, hard assignment, longer side 1024), with two changes: the model
         runs in half precision to fit an 8 GB GPU, and the vocabulary is fitted on
         our own database photos instead of the authors' "urban" one (the recipe is
         unsupervised; the authors' file sits on a share we cannot fetch by script).
Rows of the output are L2-normalised, in the order of items.jsonl.
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
import torchvision.transforms as tfm
from PIL import Image, ImageOps

MEGALOC = "gmberton/MegaLoc:5fe0dd697c4a70ba3e23607f6716ab3c606b16db"
NORM = tfm.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
VOCAB_PHOTOS, VOCAB_PATCHES, CLUSTERS, LONG_SIDE = 160, 1000, 32, 1024


def load(path):
    return tfm.functional.to_tensor(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))


def megaloc(items, dev):
    model = torch.hub.load(MEGALOC, "get_trained_model", trust_repo=True).to(dev).eval()
    out = []
    with torch.inference_mode():
        for n, it in enumerate(items):
            x = tfm.functional.resize(NORM(load(it["path"])), [322, 322], antialias=True)
            out.append(model(x[None].to(dev))[0].float().cpu().numpy())
            if n % 100 == 0:
                print(n, flush=True)
    return np.stack(out)


def anyloc(items, dev, clone, vocab_dir):
    sys.path.insert(0, str(Path(clone) / "demo"))
    from utilities import VLAD, DinoV2ExtractFeatures

    ext = DinoV2ExtractFeatures("dinov2_vitg14", 31, "value", device=dev)
    ext.dino_model = ext.dino_model.half()

    def patches(path):
        x = NORM(load(path))
        h, w = x.shape[-2:]
        s = LONG_SIDE / max(h, w)
        x = tfm.functional.resize(x, [int(h * s) // 14 * 14, int(w * s) // 14 * 14], antialias=True)
        return ext(x[None].to(dev).half())[0].float().cpu()

    torch.manual_seed(0)
    db = [it for it in items if it["role"] == "db"]
    vlad = VLAD(CLUSTERS, desc_dim=None, cache_dir=vocab_dir)
    if not vlad.can_use_cache_vlad():
        step = max(1, len(db) // VOCAB_PHOTOS)
        g = torch.Generator().manual_seed(0)
        train = []
        for it in db[::step][:VOCAB_PHOTOS]:
            d = patches(it["path"])
            train.append(d[torch.randperm(len(d), generator=g)[:VOCAB_PATCHES]])
        vlad.fit(torch.cat(train))
    else:
        vlad.fit(None)
    vlad.c_centers = vlad.c_centers.cpu()
    vlad.kmeans.centroids = vlad.c_centers
    out = []
    for n, it in enumerate(items):
        out.append(F.normalize(vlad.generate(patches(it["path"])), dim=0).numpy())
        if n % 100 == 0:
            print(n, flush=True)
    return np.stack(out)


def main(argv):
    items = [json.loads(line) for line in Path(argv[1]).read_text().splitlines()]
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(len(items), "photos on", dev, flush=True)
    d = megaloc(items, dev) if argv[0] == "megaloc" else anyloc(items, dev, argv[3], argv[4])
    np.save(argv[2], d.astype(np.float32))


if __name__ == "__main__":
    main(sys.argv[1:])
