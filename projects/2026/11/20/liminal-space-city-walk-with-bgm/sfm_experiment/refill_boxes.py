"""refill_boxes.py <photo> <out png> <work dir> <pipeline dir> <lama model> <x0,y0,x1,y1> ...
Fill hand-drawn boxes (pixels of the photo: people the detector missed) with LaMa, each inside its own crop
(the box plus PAD pixels of context), and paste the crops back. Runs on the CPU in seconds."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, sys.argv[4])
import people_removal as pr
src, out, work = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
PAD = 300
im = Image.open(src).convert("RGB")
W, H = im.size
for i, spec in enumerate(sys.argv[6:]):
    x0, y0, x1, y1 = (int(v) for v in spec.split(","))
    cx0, cy0 = max(0, x0 - PAD) // 8 * 8, max(0, y0 - PAD) // 8 * 8
    cx1, cy1 = min(W, x1 + PAD), min(H, y1 + PAD)
    cx1, cy1 = cx0 + (cx1 - cx0) // 8 * 8, cy0 + (cy1 - cy0) // 8 * 8
    crop = im.crop((cx0, cy0, cx1, cy1))
    mask = np.zeros((cy1 - cy0, cx1 - cx0), np.uint8)
    mask[y0 - cy0:y1 - cy0, x0 - cx0:x1 - cx0] = 255
    stem = f"{src.stem[:3]}_{i}"
    crop.save(work / f"{stem}.png")
    pr.grow_mask(Image.fromarray(mask)).save(work / f"{stem}_mask_grown.png")
    pr.lama_fill(sys.argv[5], work, [(str(work / f"{stem}.png"), str(work / f"{stem}_mask_grown.png"))])
    im.paste(Image.open(work / f"{stem}_nopeople.png").convert("RGB"), (cx0, cy0))
im.save(out)
