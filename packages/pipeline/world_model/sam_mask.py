"""python -m world_model.sam_mask <camera_truth.json> [--model=facebook/sam-vit-base]
SAM's masks of each kept photo's target building, from the prompt silhouette_pose wrote (photo["silhouette"]
["prompt"]: a point in the building and its box, in full-resolution pixels), written as PNGs beside the photo
(masks/<photo stem>_<k>.png, all three SAM gives) and listed in the file. SAM runs with no sampling, on the CPU,
with deterministic kernels: the same photo and prompt give the same masks.

Needs torch and transformers, which the pipeline's own environment does not carry: run it from an environment that
has them (camera_truth/README.md)."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def masks_for(photo_path, point, box, model="facebook/sam-vit-base"):
    """The three masks (bool, full resolution) and SAM's own scores for them."""
    import torch
    from transformers import SamModel, SamProcessor
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(0)
    proc = SamProcessor.from_pretrained(model)
    net = SamModel.from_pretrained(model).eval()
    img = Image.open(photo_path).convert("RGB")
    inp = proc(img, input_points=[[point]], input_boxes=[[box]], return_tensors="pt")
    with torch.no_grad():
        out = net(**inp, multimask_output=True)
    masks = proc.image_processor.post_process_masks(out.pred_masks, inp["original_sizes"], inp["reshaped_input_sizes"])
    return masks[0][0].numpy().astype(bool), out.iou_scores[0, 0].numpy()


def main(argv):
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in argv if a.startswith("--"))
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    model = opts.get("model", "facebook/sam-vit-base")
    path = Path(args[0]); doc = json.loads(path.read_text())
    (path.parent / "masks").mkdir(exist_ok=True)
    for photo in doc["photos"]:
        p = photo.get("silhouette", {}).get("prompt")
        if not p:
            continue
        masks, scores = masks_for(path.parent / photo["file"], p["point"], p["box"], model)
        names = []
        for k, m in enumerate(masks):
            name = f"masks/{Path(photo['file']).stem}_{k}.png"
            Image.fromarray((m * 255).astype(np.uint8)).convert("1").save(path.parent / name, optimize=True)
            names.append(name)
        photo["silhouette"].update(masks=names, sam_model=model, sam_scores=[round(float(s), 3) for s in scores])
        print(photo["ref"], names, photo["silhouette"]["sam_scores"])
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
