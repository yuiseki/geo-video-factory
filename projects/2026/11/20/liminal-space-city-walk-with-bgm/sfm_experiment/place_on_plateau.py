"""place_on_plateau.py <sparse_model_dir> <place.json of place_on_footprints.py> <plateau tris.npz> <out_prefix>
Experiment: the outline fit leaves the scale open (a wall slides along a wall). Fix it in 3D: for a row of
scales, start from the outline solution, optimise yaw and shift (x, y, z) so that the model's points lie on
PLATEAU surfaces (trimmed mean distance, in model units), and see whether the cost has one minimum."""
import zlib  # noqa: F401
import json
import sys

import numpy as np
import pycolmap
from scipy import optimize
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rec = pycolmap.Reconstruction(sys.argv[1])
pl = json.load(open(sys.argv[2]))
tris = np.load(sys.argv[3])["tris"].astype(np.float64)
prefix = sys.argv[4]
B, c0 = np.array(pl["basis"]), np.array(pl["centroid"])
C = np.array([im.projection_center() for im in rec.images.values()]) @ B.T
P = np.array([p.xyz for p in rec.points3D.values()]) @ B.T
col = np.array([p.color for p in rec.points3D.values()]) / 255
zc = np.median(C[:, 2]); P[:, 2] -= zc; C[:, 2] -= zc

# PLATEAU surface samples within 160 m, about one per 0.5 m x 0.5 m
ctr = tris.mean(1)
tris = tris[np.hypot(ctr[:, 0], ctr[:, 1]) < 160]
e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
area = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
rng = np.random.default_rng(0)
cnt = rng.poisson(area / 0.25)
idx = np.repeat(np.arange(len(tris)), cnt)
u, v = rng.random(len(idx)), rng.random(len(idx))
f = u + v > 1; u[f], v[f] = 1 - u[f], 1 - v[f]
S = tris[idx, 0] + u[:, None] * e1[idx] + v[:, None] * e2[idx]
tree = cKDTree(S)
ground = np.percentile(tris[..., 2], 1)

q0 = pl["solutions"][0]
gs = pl["gps_scale"]
use = P[(P[:, 2] * q0["s"] > 3)]
use = use[rng.choice(len(use), min(4000, len(use)), replace=False)]
KEEP = 0.7


def place(X, yaw, s, t):
    c, sn = np.cos(yaw), np.sin(yaw)
    xy = s * (X[:, :2] - c0) @ np.array([[c, sn], [-sn, c]]) + t[:2]
    return np.c_[xy, s * X[:, 2] + t[2]]


def cost(yaw, s, t):
    d = tree.query(place(use, yaw, s, t), distance_upper_bound=30.0)[0]
    return np.sort(np.minimum(d, 30.0))[:int(KEEP * len(use))].mean() / s


rows = []
for s in np.geomspace(2.4, 7.0, 24):
    best = None
    for q in pl["solutions"][:3]:
        x0 = [q["yaw"], q["t"][0], q["t"][1], ground + 1.5]
        r = optimize.minimize(lambda v: cost(v[0], s, v[1:]), x0, method="Nelder-Mead",
                              options=dict(xatol=1e-3, fatol=1e-5, maxiter=500, initial_simplex=np.array(x0) + np.vstack(
                                  [np.zeros(4), np.diag([np.radians(4), 4, 4, 2])])))
        if best is None or r.fun < best.fun:
            best = r
    d = tree.query(place(use, best.x[0], s, best.x[1:]))[0]
    rows.append(dict(s=float(s), cost=float(best.fun), yaw=float(best.x[0]), t=best.x[1:].tolist(),
                     median_m=float(np.median(d)), within_1m=float((d < 1).mean()),
                     eye_above_ground=float(best.x[3] - ground)))
    print(f"scale {s:5.2f}  cost {best.fun:.4f}  median {np.median(d):.2f} m  within 1 m {100 * (d < 1).mean():3.0f}%  "
          f"yaw {np.degrees(best.x[0]) % 360:6.1f}  cameras {best.x[3] - ground:5.1f} m above the PLATEAU ground", flush=True)
b = min(rows, key=lambda r: r["cost"])
r = optimize.minimize(lambda v: cost(v[0], np.exp(v[1]), v[2:]), [b["yaw"], np.log(b["s"]), *b["t"]], method="Nelder-Mead",
                      options=dict(xatol=1e-4, fatol=1e-6, maxiter=1500))
yaw, s, t = r.x[0], float(np.exp(r.x[1])), r.x[2:]
d = tree.query(place(use, yaw, s, t))[0]
Cw, Pw = place(C, yaw, s, t), place(P, yaw, s, t)
print(f"free: scale {s:.3f} m/unit  cost {r.fun:.4f}  median {np.median(d):.2f} m  within 1 m {100 * (d < 1).mean():.0f}%  "
      f"within 2 m {100 * (d < 2).mean():.0f}%  cameras {np.median(Cw[:, 2]) - ground:.2f} m above the PLATEAU ground "
      f"(ground {ground:.1f} m, ellipsoidal)  camera centroid {np.hypot(*t[:2]):.1f} m from the GPS centroid")
json.dump(dict(origin=pl["origin"], basis=pl["basis"], centroid=pl["centroid"], z_cam_median=float(zc), yaw=float(yaw),
               scale=s, t=[float(x) for x in t], ground=float(ground), scan=rows), open(prefix + ".json", "w"), indent=1)

fig, ax = plt.subplots(1, 3, figsize=(21, 7.5), dpi=100)
ax[0].plot([r["s"] for r in rows], [r["cost"] for r in rows], "o-", color="#1f77b4")
ax[0].axvline(s, color="#d62728", lw=0.8); ax[0].set_xlabel("scale (m per model unit)"); ax[0].set_ylabel("trimmed mean distance to PLATEAU (model units)")
ax[0].set_title("cost along the scale; yaw and shift re-optimised at each scale", fontsize=10); ax[0].grid(alpha=.3)
ax[1].scatter(S[::7, 0], S[::7, 1], s=0.3, color="#bbb", linewidths=0)
ax[1].scatter(Pw[:, 0], Pw[:, 1], s=1.5, c=col, linewidths=0); ax[1].scatter(Cw[:, 0], Cw[:, 1], s=12, color="#d62728")
ax[1].set_xlim(-120, 130); ax[1].set_ylim(-140, 110); ax[1].set_aspect("equal"); ax[1].grid(alpha=.3)
ax[1].set_title(f"top view: PLATEAU (grey), model points, cameras (red). scale {s:.2f}", fontsize=10)
ax[1].set_xlabel("east (m)"); ax[1].set_ylabel("north (m)")
near = tree.query(Pw)[0] < 3
west = S[(S[:, 0] > 20) & (S[:, 0] < 60) & (S[:, 1] > -100) & (S[:, 1] < 40)]
ax[2].scatter(west[::3, 1], west[::3, 2] - ground, s=0.4, color="#bbb", linewidths=0)
ax[2].scatter(Pw[near, 1], Pw[near, 2] - ground, s=2, c=col[near], linewidths=0)
ax[2].set_xlim(-110, 50); ax[2].set_ylim(-5, 80); ax[2].set_aspect("equal"); ax[2].grid(alpha=.3)
ax[2].set_title("looking east: PLATEAU at x 20-60 m (grey), model points within 3 m of it", fontsize=10)
ax[2].set_xlabel("north (m)"); ax[2].set_ylabel("height above the PLATEAU ground (m)")
fig.tight_layout(); fig.savefig(prefix + ".png"); print("saved", prefix + ".png")
