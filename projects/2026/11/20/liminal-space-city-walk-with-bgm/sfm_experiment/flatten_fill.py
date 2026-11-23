"""flatten_fill.py <filled photo> <mask_grown.png> <out.png> [--below=0.62] [--right=1.0] [--sx=0.04] [--sy=0.012]
Where LaMa filled a crowd standing on the road, its fill ripples. Below the row --below (fraction of the height)
the filled pixels are replaced by a strong blur of themselves (wider than high: a road changes with distance, not
sideways) plus a little grain. The fill stays a guess; it only stops drawing attention."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage
src, mask, out = sys.argv[1:4]
o = dict(a[2:].split("=", 1) for a in sys.argv[4:])
im = np.asarray(Image.open(src).convert("RGB")).astype(np.float32)
h, w = im.shape[:2]
m = np.asarray(Image.open(mask).convert("L").resize((w, h), Image.BILINEAR)).astype(np.float32) / 255
m[: int(float(o.get("below", 0.62)) * h)] = 0
# --right: only the columns left of this fraction of the width (feathered), to keep a fill that came out well
right = float(o.get("right", 1.0))
m *= np.clip((right - np.arange(w) / w) / 0.06, 0, 1)[None, :]
sx, sy = float(o.get("sx", 0.04)) * w, float(o.get("sy", 0.012)) * w
# blur only what was filled (normalised by the mask), so that kerbs and unfilled paint do not bleed in
num = np.stack([ndimage.gaussian_filter(im[..., c] * m, (sy, sx)) for c in range(3)], -1)
den = ndimage.gaussian_filter(m, (sy, sx))[..., None]
flat = num / np.maximum(den, 1e-3)
rng = np.random.default_rng(0)
grain = ndimage.gaussian_filter(rng.normal(0, 1, (h, w)), 1.2)
coarse = ndimage.gaussian_filter(rng.normal(0, 1, (h, w)), 7)
flat += (grain / grain.std() * 4.0 + coarse / coarse.std() * 2.5)[..., None]
a = ndimage.gaussian_filter(m, 0.004 * w)[..., None]
a = np.clip(a * 1.5, 0, 1)
res = im * (1 - a) + flat * a
Image.fromarray(np.clip(res, 0, 255).astype(np.uint8)).save(out)
print(f"{out}: {(a[..., 0] > 0.5).mean():.1%} of the picture flattened")
