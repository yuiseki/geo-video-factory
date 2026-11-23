"""tile_fill.py <big-lama.pt> <photo> <mask_grown> <out.png> [scale=1.0] [tile=1024]
Experiment: LaMa on overlapping tiles at (near) the photo's own resolution instead of the whole photo shrunk to 1024 px.
scale < 1 shrinks the photo first (0.5 = half resolution). Tiles that contain no mask are skipped; overlaps are
feathered. Then composited through the soft mask like people_removal.composite."""
import sys
import numpy as np
import torch
from PIL import Image
from spandrel import ModelLoader

model_path, photo_p, mask_p, out_p = sys.argv[1:5]
scale = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
T = int(sys.argv[6]) if len(sys.argv) > 6 else 1024
dev = "mps" if torch.backends.mps.is_available() else "cpu"
model = ModelLoader().load_from_file(model_path).eval().to(dev)

photo = Image.open(photo_p).convert("RGB")
soft = Image.open(mask_p).convert("L").resize(photo.size)
W, H = photo.size
w, h = int(W * scale) // 8 * 8, int(H * scale) // 8 * 8
img = np.asarray(photo.resize((w, h), Image.LANCZOS), np.float32) / 255
m = (np.asarray(soft.resize((w, h), Image.BILINEAR)) > 20).astype(np.float32)

acc = np.zeros((h, w, 3), np.float32)
wsum = np.zeros((h, w), np.float32)
step = T * 3 // 4
ys = list(range(0, max(1, h - T) + 1, step)) or [0]
xs = list(range(0, max(1, w - T) + 1, step)) or [0]
if ys[-1] + T < h: ys.append(h - T)
if xs[-1] + T < w: xs.append(w - T)
ramp = np.minimum(np.linspace(0, 1, T // 4 + 2)[1:-1], 1)
win1 = np.ones(T, np.float32); win1[:len(ramp)] = ramp; win1[-len(ramp):] = ramp[::-1]
n = 0
for y in ys:
    for x in xs:
        y0, x0 = max(0, y), max(0, x)
        y1, x1 = min(h, y0 + T), min(w, x0 + T)
        mt = m[y0:y1, x0:x1]
        if mt.sum() == 0:
            continue
        it = img[y0:y1, x0:x1]
        th, tw = it.shape[:2]
        ph, pw = (8 - th % 8) % 8, (8 - tw % 8) % 8
        itp = np.pad(it, ((0, ph), (0, pw), (0, 0)), mode="reflect")
        mtp = np.pad(mt, ((0, ph), (0, pw)))
        with torch.no_grad():
            r = model(torch.from_numpy(itp).permute(2, 0, 1)[None].to(dev),
                      torch.from_numpy(mtp)[None, None].to(dev)).clamp(0, 1).cpu()[0].permute(1, 2, 0).numpy()
        wy = win1[:th] if y0 > 0 else np.r_[np.ones(T - len(ramp)), ramp[::-1]][:th] if y1 < h else np.ones(th)
        wx = win1[:tw] if x0 > 0 else np.r_[np.ones(T - len(ramp)), ramp[::-1]][:tw] if x1 < w else np.ones(tw)
        if y0 > 0 and y1 >= h: wy = np.r_[ramp, np.ones(T)][:th]
        if x0 > 0 and x1 >= w: wx = np.r_[ramp, np.ones(T)][:tw]
        wt = np.outer(wy, wx).astype(np.float32) + 1e-4
        acc[y0:y1, x0:x1] += r[:th, :tw] * wt[..., None]
        wsum[y0:y1, x0:x1] += wt
        n += 1
fill = np.where(wsum[..., None] > 0, acc / np.maximum(wsum, 1e-6)[..., None], img)
fill_im = Image.fromarray((fill * 255).round().astype(np.uint8)).resize(photo.size, Image.LANCZOS)
Image.composite(fill_im, photo, soft).save(out_p)
print(out_p.split("/")[-1], "tiles", n, "at", w, "x", h)
