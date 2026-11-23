"""sfm_plot.py <sparse_model_dir> <out.png>
Top-down view of a COLMAP model: 3D points grey, cameras as dots with their view direction.
'Up' is the mean of the cameras' up vectors (photos are mostly held level)."""
import sys

import numpy as np
import pycolmap
from PIL import Image, ImageDraw

rec = pycolmap.Reconstruction(sys.argv[1])
cams, dirs, ups, names = [], [], [], []
for img in rec.images.values():
    w2c = img.cam_from_world()
    R = w2c.rotation.matrix()
    cams.append(img.projection_center())
    dirs.append(R.T @ np.array([0, 0, 1.0]))
    ups.append(R.T @ np.array([0, -1.0, 0]))
    names.append(img.name.split("__")[-1][:3])
cams, dirs = np.array(cams), np.array(dirs)
up = np.mean(ups, 0)
up /= np.linalg.norm(up)
a = np.cross(up, [1.0, 0, 0]) if abs(up[0]) < 0.9 else np.cross(up, [0, 1.0, 0])
a /= np.linalg.norm(a)
b = np.cross(up, a)
pts = np.array([p.xyz for p in rec.points3D.values()])
P2 = np.c_[pts @ a, pts @ b]
C2 = np.c_[cams @ a, cams @ b]
D2 = np.c_[dirs @ a, dirs @ b]
lo, hi = np.percentile(np.r_[P2, C2], 2, 0), np.percentile(np.r_[P2, C2], 98, 0)
lo, hi = np.minimum(lo, C2.min(0)), np.maximum(hi, C2.max(0))
S = 1400
k = (S - 80) / (hi - lo).max()
f = lambda q: (40 + (q[0] - lo[0]) * k, 40 + (q[1] - lo[1]) * k)
im = Image.new("RGB", (S, S), (16, 16, 20))
d = ImageDraw.Draw(im)
for q in P2:
    x, y = f(q)
    d.point((x, y), fill=(110, 110, 120))
L = 0.04 * (hi - lo).max()
for c, v, nm in zip(C2, D2, names):
    x, y = f(c)
    nv = v / (np.linalg.norm(v) + 1e-9)
    x2, y2 = f(c + nv * L)
    d.line((x, y, x2, y2), fill=(255, 200, 0), width=2)
    d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(255, 80, 60))
    d.text((x + 5, y + 3), nm, fill=(255, 255, 255))
d.text((10, 10), f"{len(cams)} cameras, {len(pts)} points (top-down, scale arbitrary)", fill=(255, 255, 0))
im.save(sys.argv[2])
