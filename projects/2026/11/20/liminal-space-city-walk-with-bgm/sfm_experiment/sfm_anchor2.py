"""sfm_anchor.py <sparse_model> <plateau_tris.npz> <camera_fit.json> <image_name_substring> <out_prefix>
Experiment: place a COLMAP model on PLATEAU from ONE camera whose position and bearing were fitted to PLATEAU by
hand earlier (camera_018.json). Level by the mean camera 'up', turn so the anchor camera looks along its fitted
bearing, put it at its fitted eye, then search the scale (and a little yaw) by trimmed ICP to PLATEAU surfaces.
Reports the median distance of model points to the nearest PLATEAU surface."""
import json
import sys

import numpy as np
import pycolmap
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

rec = pycolmap.Reconstruction(sys.argv[1])
z = np.load(sys.argv[2])
tris, (lon0, lat0) = z["tris"].astype(np.float64), z["origin"]
fit = json.load(open(sys.argv[3]))["fit"]
anchor_key, prefix = sys.argv[4], sys.argv[5]

names, C, UP, FW, RIGHTS = [], [], [], [], []
for img in rec.images.values():
    R = img.cam_from_world().rotation.matrix()
    names.append(img.name)
    C.append(img.projection_center())
    UP.append(R.T @ np.array([0, -1.0, 0]))
    RIGHTS.append(R.T @ np.array([1.0, 0, 0]))
    FW.append(R.T @ np.array([0, 0, 1.0]))
C, FW = np.array(C), np.array(FW)
ai = [i for i, n in enumerate(names) if anchor_key in n][0]
pts = np.array([p.xyz for p in rec.points3D.values() if p.track.length() >= 3 and p.error < 2.0])
# camera x axes stay horizontal however the camera pitches: up is their common normal
up = np.linalg.svd(np.array(RIGHTS))[2][-1]
up = up if up @ np.mean(UP, 0) > 0 else -up


def rot_to_z(u):
    zz = np.array([0, 0, 1.0])
    v = np.cross(u, zz)
    s = np.linalg.norm(v)
    if s < 1e-9:
        return np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]]) / s
    a = np.arctan2(s, u @ zz)
    return np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * K @ K


def rz(phi):
    c, s = np.cos(phi), np.sin(phi)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


R0 = rot_to_z(up)
P = (pts - C[ai]) @ R0.T
Cl = (C - C[ai]) @ R0.T
f = FW[ai] @ R0.T
heading = np.arctan2(f[0], f[1])
bearing = np.radians(fit["bearing"])
yaw0 = heading - bearing

# anchor eye in the local ENU frame (small-area approximation is fine within 1 km)
lon, lat, h = fit["eye"]
e = np.radians(lon - lon0) * 6378137 * np.cos(np.radians(lat0))
n = np.radians(lat - lat0) * 6378137
ground = np.percentile(tris[..., 2], 1)
eye = np.array([e, n, ground + h])
print(f"anchor {names[ai]} at E{e:.1f} N{n:.1f}; leveled tilt of anchor {np.degrees(np.arcsin(f[2])):.1f} deg "
      f"(fit said {fit['tilt'] - 90:.1f})")

rng = np.random.default_rng(0)
a = np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1) / 2
n_s = 600000
idx = rng.choice(len(tris), n_s, p=a / a.sum())
u, v = rng.random(n_s), rng.random(n_s)
fl = u + v > 1
u[fl], v[fl] = 1 - u[fl], 1 - v[fl]
T = tris[idx]
S = T[:, 0] + u[:, None] * (T[:, 1] - T[:, 0]) + v[:, None] * (T[:, 2] - T[:, 0])
tree = cKDTree(S)


def umeyama(X, Y):
    mx, my = X.mean(0), Y.mean(0)
    Xc, Yc = X - mx, Y - my
    U_, D, Vt = np.linalg.svd(Yc.T @ Xc / len(X))
    Sg = np.eye(3)
    if np.linalg.det(U_) * np.linalg.det(Vt) < 0:
        Sg[2, 2] = -1
    Rm = U_ @ Sg @ Vt
    return np.trace(np.diag(D) @ Sg) / Xc.var(0).sum(), Rm, my - (np.trace(np.diag(D) @ Sg) / Xc.var(0).sum()) * Rm @ mx
# roof height raster (1 m cells): max z of PLATEAU triangles; 0 = no building
RES, N = 1.0, 2000
HALF = RES * N / 2
roof_im = Image.new("F", (N, N), 0.0)
rd = ImageDraw.Draw(roof_im)
order = np.argsort(tris[..., 2].max(1))
for tr in tris[order]:
    rd.polygon([((x + HALF) / RES, (HALF - y) / RES) for x, y, _ in tr], fill=float(tr[:, 2].max()))
roof = np.asarray(roof_im)


def inside(Y, dd=None):
    ix = np.clip(((Y[:, 0] + HALF) / RES).astype(int), 0, N - 1)
    iy = np.clip(((HALF - Y[:, 1]) / RES).astype(int), 0, N - 1)
    r = roof[iy, ix]
    res = (r > 0) & (Y[:, 2] < r - 1.5) & (Y[:, 2] > ground)
    if dd is not None:
        res &= dd > 1.5
    return res


def score(s, Rm, t):
    Y = s * P @ Rm.T + t
    dd, _ = tree.query(Y, distance_upper_bound=50)
    dd[~np.isfinite(dd)] = 50
    cam = s * Cl @ Rm.T + t
    near = np.mean(dd < 1.5)
    pin = np.mean(inside(Y, dd))
    cin = np.mean(inside(cam))
    return near - 2 * pin - cin, near, pin, cin, dd


ext = np.percentile(np.linalg.norm(P[:, :2], axis=1), 50)
coarse = []
for s in np.geomspace(18, 75, 25):
    for dy in np.radians(np.arange(-12, 13, 3)):
        J, near, pin, cin, _ = score(s, rz(yaw0 + dy), eye)
        coarse.append((J, s, dy, near, pin, cin))
coarse.sort(key=lambda c: -c[3])
print("coarse best (J, scale, yaw jitter, near<1.5m, points inside, cameras inside):")
for c in coarse[:6]:
    print(f"  {c[0]:6.3f} {c[1]:7.2f} {np.degrees(c[2]):5.1f}  {c[3]:.0%} {c[4]:.0%} {c[5]:.0%}")


def icp(s, Rm, t, iters=40):
    for _ in range(iters):
        Y = s * P @ Rm.T + t
        dd, j = tree.query(Y)
        sel = dd <= max(np.percentile(dd, 60), 0.3)
        s2, R2, t2 = umeyama(Y[sel], S[j[sel]])
        s, Rm, t = s2 * s, R2 @ Rm, s2 * R2 @ t + t2
    return s, Rm, t


best = None
seen = []
solutions = []
for c in coarse:
    if any(abs(np.log(c[1] / q)) < 0.1 for q in seen):
        continue
    seen.append(c[1])
    s1, R1, t1 = icp(c[1], rz(yaw0 + c[2]), eye.copy())
    J, near, pin, cin, dd = score(s1, R1, t1)
    moved = np.linalg.norm(s1 * Cl[ai] @ R1.T + t1 - eye)
    print(f"  ICP from scale {c[1]:.2f}: scale {s1:.2f}  J {J:.3f}  median {np.median(dd):.2f} m  near {near:.0%}  "
          f"pts inside {pin:.0%}  cams inside {cin:.0%}  anchor moved {moved:.1f} m")
    solutions.append({'scale': s1, 'R': R1.tolist(), 't': t1.tolist(), 'median': float(np.median(dd))})
    if best is None or J > best[3]:
        best = (s1, R1, t1, J, dd)
    if len(seen) >= 5:
        break
s, Rm, t, J, dd = best
med = np.median(dd)
cams = s * Cl @ Rm.T + t
json.dump({"solutions": solutions, "scale": s, "R_level": R0.tolist(), "R": Rm.tolist(), "t": t.tolist(), "model_anchor": C[ai].tolist(),
           "median_m": float(med), "within_1m": float(np.mean(dd < 1)), "within_2m": float(np.mean(dd < 2)),
           "ground_z": ground, "cameras": {nm: c.tolist() for nm, c in zip(names, cams)}},
          open(prefix + ".json", "w"), indent=1)

V = 900
img = Image.new("RGB", (V, V), (16, 16, 20))
dr = ImageDraw.Draw(img)
cx, cy = 60.0, -100.0
g = lambda x, y: (x - cx + V / 2, cy - y + V / 2)
for tr in tris:
    if abs(tr[0, 0] - cx) < V and abs(tr[0, 1] - cy) < V:
        dr.polygon([g(x, y) for x, y, _ in tr], fill=(60, 60, 66))
Y = s * P @ Rm.T + t
for (x, y, _), d_ in zip(Y, dd):
    dr.point(g(x, y), fill=(0, 230, 120) if d_ < 1 else (255, 200, 0) if d_ < 3 else (255, 60, 200))
for nm, (x, y, _) in zip(names, cams):
    X, Yp = g(x, y)
    dr.ellipse((X - 3, Yp - 3, X + 3, Yp + 3), fill=(255, 70, 50))
    dr.text((X + 4, Yp), nm.split("__")[-1][:3], fill=(255, 255, 255))
X, Yp = g(0, 0)
dr.line((X - 8, Yp, X + 8, Yp), fill=(120, 160, 255))
dr.line((X, Yp - 8, X, Yp + 8), fill=(120, 160, 255))
dr.text((8, 8), f"1 px = 1 m, north up, blue + = crossing centre. points: green <1 m, yellow <3 m, pink farther. "
        f"median {med:.2f} m", fill=(255, 255, 0))
img.save(prefix + "_top.png")
