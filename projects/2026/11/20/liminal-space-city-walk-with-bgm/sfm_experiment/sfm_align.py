"""sfm_align.py <sparse_model> <plateau_tris.npz> <out_prefix>
Experiment: place a COLMAP model on PLATEAU without hand-picked points.
1. level: rotate so the mean camera 'up' is +z (photos are mostly held level)
2. 2D search: for each yaw and scale, FFT cross-correlation of the model's points (top view) with a map that is
   high near PLATEAU building outlines, which gives the best translation; keep the best few
3. 3D refine: trimmed ICP with a similarity transform (Umeyama) against points sampled on PLATEAU triangles
Writes <out_prefix>.json (transform, residuals, camera positions) and prints a summary."""
import json
import sys

import numpy as np
import pycolmap
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import cKDTree

rec = pycolmap.Reconstruction(sys.argv[1])
tris = np.load(sys.argv[2])["tris"].astype(np.float64)
prefix = sys.argv[3]

# --- model
names, C, UP = [], [], []
for img in rec.images.values():
    R = img.cam_from_world().rotation.matrix()
    names.append(img.name)
    C.append(img.projection_center())
    UP.append(R.T @ np.array([0, -1.0, 0]))
C = np.array(C)
pts, errs, tl = [], [], []
for p in rec.points3D.values():
    pts.append(p.xyz)
    errs.append(p.error)
    tl.append(p.track.length())
pts = np.array(pts)
keep = (np.array(tl) >= 3) & (np.array(errs) < 2.0)
pts = pts[keep]
up = np.mean(UP, 0)
up /= np.linalg.norm(up)


def rot_to_z(u):
    z = np.array([0, 0, 1.0])
    v = np.cross(u, z)
    s, c = np.linalg.norm(v), u @ z
    if s < 1e-9:
        return np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]]) / s
    a = np.arctan2(s, c)
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


R0 = rot_to_z(up)
centre = np.median(C, 0)
P = (pts - centre) @ R0.T
Cl = (C - centre) @ R0.T
print("model points", len(P), "cameras", len(C))

# --- PLATEAU outline map (top view)
RES, N = 4.0, 512
HALF = RES * N / 2
mask = Image.new("L", (N, N), 0)
d = ImageDraw.Draw(mask)
for t in tris:
    xy = [((x + HALF) / RES, (HALF - y) / RES) for x, y, _ in t]
    d.polygon(xy, fill=255)
m = np.asarray(mask) > 0
edge = m & ~ndimage.binary_erosion(m)
dist = ndimage.distance_transform_edt(~edge) * RES
score = np.exp(-dist / 6.0) - 0.3
F = np.fft.rfft2(score)

# --- 2D search
ext = np.percentile(np.linalg.norm(P[:, :2], axis=1), 90)
scales = np.geomspace(60 / ext, 700 / ext, 40)
results = []
for s in scales:
    for yaw in np.radians(np.arange(0, 360, 2)):
        c, si = np.cos(yaw), np.sin(yaw)
        q = s * (P[:, :2] @ np.array([[c, si], [-si, c]]))
        ix = np.floor(q[:, 0] / RES).astype(int) % N
        iy = np.floor(-q[:, 1] / RES).astype(int) % N
        occ = np.zeros((N, N))
        occ[iy, ix] = 1
        corr = np.fft.irfft2(F * np.conj(np.fft.rfft2(occ)), s=(N, N))
        k = np.argmax(corr)
        ty, tx = divmod(k, N)
        results.append((corr.flat[k], s, yaw, tx * RES - HALF, HALF - ty * RES))
results.sort(key=lambda r: -r[0])
print("best 2D candidates (score, scale, yaw deg, east, north):")
for r in results[:8]:
    print(f"  {r[0]:7.1f} {r[1]:.3f} {np.degrees(r[2]):5.0f} {r[3]:7.1f} {r[4]:7.1f}")

# --- 3D refine
rng = np.random.default_rng(0)
a = np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1) / 2
n_s = 400000
idx = rng.choice(len(tris), n_s, p=a / a.sum())
u, v = rng.random(n_s), rng.random(n_s)
flip = u + v > 1
u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
T = tris[idx]
S = T[:, 0] + u[:, None] * (T[:, 1] - T[:, 0]) + v[:, None] * (T[:, 2] - T[:, 0])
tree = cKDTree(S)
ground = np.percentile(tris[..., 2], 1)


def umeyama(X, Y):
    mx, my = X.mean(0), Y.mean(0)
    Xc, Yc = X - mx, Y - my
    U_, D, Vt = np.linalg.svd(Yc.T @ Xc / len(X))
    Sg = np.eye(3)
    if np.linalg.det(U_) * np.linalg.det(Vt) < 0:
        Sg[2, 2] = -1
    Rm = U_ @ Sg @ Vt
    sc = np.trace(np.diag(D) @ Sg) / Xc.var(0).sum()
    return sc, Rm, my - sc * Rm @ mx


def refine(cand):
    _, s, yaw, tx, ty = cand
    c, si = np.cos(yaw), np.sin(yaw)
    Rm = np.array([[c, si, 0], [-si, c, 0], [0, 0, 1.0]])
    # start with the camera cluster at eye height above the ground
    t = np.array([tx, ty, ground + 1.6 - s * np.median(Cl[:, 2])])
    for it in range(40):
        Y = s * P @ Rm.T + t
        dd, j = tree.query(Y)
        thr = np.percentile(dd, 70)
        sel = dd <= max(thr, 0.5)
        s2, R2, t2 = umeyama(Y[sel], S[j[sel]])
        s, Rm, t = s2 * s, R2 @ Rm, s2 * R2 @ t + t2
    dd, _ = tree.query(s * P @ Rm.T + t)
    return s, Rm, t, dd


best = None
for cand in results[:6]:
    s, Rm, t, dd = refine(cand)
    med = np.median(dd)
    print(f"  refine from yaw {np.degrees(cand[2]):4.0f}: scale {s:.3f}  median {med:.2f} m  "
          f"<1m {np.mean(dd < 1):.0%}  <3m {np.mean(dd < 3):.0%}")
    if best is None or med < best[3]:
        best = (s, Rm, t, med, dd)
s, Rm, t, med, dd = best
cams = s * Cl @ Rm.T + t
out = {"scale": s, "R": (Rm @ R0).tolist(), "centre": centre.tolist(), "t": t.tolist(),
       "median_m": med, "within_1m": float(np.mean(dd < 1)), "within_3m": float(np.mean(dd < 3)),
       "ground_z": ground, "cameras": {n: c.tolist() for n, c in zip(names, cams)}}
json.dump(out, open(prefix + ".json", "w"), indent=1)

# --- top view picture
img = Image.fromarray(np.where(m, 70, 18).astype(np.uint8)).convert("RGB").resize((N * 2, N * 2), Image.NEAREST)
dr = ImageDraw.Draw(img)
f = lambda x, y: ((x + HALF) / RES * 2, (HALF - y) / RES * 2)
Y = s * P @ Rm.T + t
for x, y, _ in Y[::2]:
    dr.point(f(x, y), fill=(0, 220, 255))
for n, (x, y, z) in zip(names, cams):
    X, Yp = f(x, y)
    dr.ellipse((X - 3, Yp - 3, X + 3, Yp + 3), fill=(255, 70, 50))
    dr.text((X + 4, Yp), n.split("__")[-1][:3], fill=(255, 255, 255))
dr.text((8, 8), f"PLATEAU (grey) + SfM points (cyan) + cameras (red). median {med:.2f} m", fill=(255, 255, 0))
img.crop((N // 2, N // 2, N * 3 // 2, N * 3 // 2)).save(prefix + "_top.png")
print("saved", prefix + ".json")
