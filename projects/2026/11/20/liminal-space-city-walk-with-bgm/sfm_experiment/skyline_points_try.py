"""skyline_points_try.py <photos.npz> <model_grid.npz> <sparse_model_dir> <placement.json> <plateau tris.npz> <out_dir> <fit ids>
Experiment: the roofline and the SfM points each leave something open when a model is placed on PLATEAU.
The points lie on the walls equally well in two places 22 m apart along a gently curved facade (they cannot
tell which), and the roofline says little about the scale. Neither answer alone satisfies the other: the
skyline's best move leaves the points 1.8 m off the walls, and refitting the points afterwards walks the
cameras 2 m out of the skyline's valley. So search them together.
The cameras are moved together (one scale and one turn about their centre, one shift). The skyline cost of the
photos in <fit ids> is read on the grid of model_grid.npz for every move (as skyline_refit_try.py). Then, inside
each of the best cells of that search (half a step each way in scale, turn and shift), the move is refined to
the smallest trimmed mean distance of the SfM points to the PLATEAU surfaces. A move is good when both are low.
photos.npz and placement.json must belong together (skyline_match_try.py writes the former from the latter).
Writes combined.json (every cell) and placement_combined.json (the cell with the lowest skyline cost + points
median, in degrees and metres; the choice barely depends on the weight, see the printed lists)."""
import zlib  # noqa: F401
import json
import sys
from pathlib import Path

import numpy as np
import pycolmap
from scipy import optimize
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import skyline_match as sm  # noqa: E402

ph, z = np.load(sys.argv[1]), np.load(sys.argv[2])
rec = pycolmap.Reconstruction(sys.argv[3])
pl = json.load(open(sys.argv[4]))
tris = np.load(sys.argv[5])["tris"].astype(float)
out = Path(sys.argv[6])
out.mkdir(parents=True, exist_ok=True)
fit_ids = sys.argv[7].split(",")
names = [str(n)[-7:-4] for n in ph["names"]]
eyes, BINS, ground = ph["eyes"], int(ph["bins"]), float(ph["ground"])
photos = [dict(sky=ph["sky"][i], floor=ph["floor"][i], ceil=ph["ceil"][i]) for i in range(len(names))]
places = z["places"]
xs, ys, zs = np.unique(places[:, 0]), np.unique(places[:, 1]), np.unique(places[:, 2])
G = z["skyline"].reshape(len(zs), len(ys), len(xs), BINS)
pivot = eyes.mean(0)

SCALES = np.arange(0.80, 1.4001, 0.025)
TURNS = np.arange(-24, 13) * 360 / BINS        # degrees, clockwise
DX, DY, DZ = np.arange(-14, 15, 2.0), np.arange(-36, 13, 2.0), np.array([-4.5, -3.0, -1.5, 0.0, 1.5])
HALF = np.array([0.0125, 0.25, 1.0, 1.0, 0.75])  # half a cell: scale, turn, east, north, up
CELLS, MARGIN, KEEP = 400, 0.5, 0.7


def put(X, q):
    """The move q = scale, turn (deg, clockwise), east, north, up applied to world points."""
    th = np.radians(q[1])
    Q = np.array([[np.cos(th), np.sin(th), 0], [-np.sin(th), np.cos(th), 0], [0, 0, 1]])
    return pivot + q[0] * (X - pivot) @ Q.T + q[2:5]


def skyline_costs(i, scale, turn):
    """The skyline cost of photo i for every shift (dz, dy, dx); inf where the grid does not reach."""
    e = put(eyes[i], np.array([scale, turn, 0, 0, 0]))
    ix = np.round((e[0] + DX - xs[0]) / (xs[1] - xs[0])).astype(int)
    iy = np.round((e[1] + DY - ys[0]) / (ys[1] - ys[0])).astype(int)
    iz = np.round((e[2] + DZ - zs[0]) / (zs[1] - zs[0])).astype(int)
    ok = (((iz >= 0) & (iz < len(zs)))[:, None, None] & ((iy >= 0) & (iy < len(ys)))[None, :, None]
          & ((ix >= 0) & (ix < len(xs)))[None, None, :])
    sub = G[np.clip(iz, 0, len(zs) - 1)][:, np.clip(iy, 0, len(ys) - 1)][:, :, np.clip(ix, 0, len(xs) - 1)]
    shift = [int(round(turn * BINS / 360)) % BINS]
    c = sm.match_cost(photos[i], sub.reshape(-1, BINS), tau=5.0, shifts=shift).reshape(ok.shape)
    return np.where(ok, c, np.inf)


fit = [names.index(n) for n in fit_ids]
cells = []
for sc in SCALES:
    for tn in TURNS:
        J = np.mean([skyline_costs(i, sc, tn) for i in fit], axis=0)
        for k in np.argsort(J.ravel())[:3]:  # the three best shifts of every scale and turn
            iz, iy, ix = np.unravel_index(k, J.shape)
            cells.append((float(J[iz, iy, ix]), sc, tn, DX[ix], DY[iy], DZ[iz]))
cells.sort()
cells = [c for c in cells if c[0] <= cells[0][0] + MARGIN][:CELLS]
print(f"{len(cells)} cells, skyline cost from {cells[0][0]:.3f} to {cells[-1][0]:.3f}", flush=True)

# the SfM points in the world of the placement, and samples of the PLATEAU surfaces
B, o = np.array(pl["basis"]), np.array([*pl["centroid"], pl["z_cam_median"]])
c, s = np.cos(pl["yaw"]), np.sin(pl["yaw"])
A = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
P = np.array([p.xyz for p in rec.points3D.values() if p.track.length() >= 3])
Pw = pl["scale"] * (P @ B.T - o) @ A.T + np.array(pl["t"])
ctr = tris.mean(1)
tris = tris[np.hypot(ctr[:, 0], ctr[:, 1]) < 200]
e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
rng = np.random.default_rng(0)
idx = np.repeat(np.arange(len(tris)), rng.poisson(0.5 * np.linalg.norm(np.cross(e1, e2), axis=1) / 0.25))
u, v = rng.random(len(idx)), rng.random(len(idx))
f = u + v > 1
u[f], v[f] = 1 - u[f], 1 - v[f]
tree = cKDTree(tris[idx, 0] + u[:, None] * e1[idx] + v[:, None] * e2[idx])
use = Pw[Pw[:, 2] > ground + 3]
use = use[rng.choice(len(use), min(2500, len(use)), replace=False)]


def points_cost(q):
    d = tree.query(put(use, q), distance_upper_bound=30.0)[0]
    return np.sort(np.minimum(d, 30.0))[:int(KEEP * len(use))].mean()


rows = []
for cell in cells:
    q0 = np.array(cell[1:])
    r = optimize.minimize(points_cost, q0, method="Powell", bounds=list(zip(q0 - HALF, q0 + HALF)),
                          options=dict(xtol=1e-3, ftol=1e-4, maxfev=400))
    d = tree.query(put(use, r.x))[0]
    rows.append(dict(skyline=cell[0], cell=[float(x) for x in cell[1:]], move=[float(x) for x in r.x],
                     points_trimmed_m=float(r.fun), points_median_m=float(np.median(d)), within_1m=float((d < 1).mean()),
                     eye_above_ground=float(np.median(put(eyes, r.x)[:, 2]) - ground)))
json.dump(rows, open(out / "combined.json", "w"), indent=1)


def show(r):
    q = r["move"]
    print(f"  skyline {r['skyline']:.3f}  points median {r['points_median_m']:.2f} m, within 1 m {100 * r['within_1m']:.0f}%  "
          f"scale x{q[0]:.3f} turn {q[1]:+.2f} deg east {q[2]:+.1f} north {q[3]:+.1f} up {q[4]:+.2f}  cameras {r['eye_above_ground']:.2f} m")


d = tree.query(use)[0]
print(f"as placed: points median {np.median(d):.2f} m, within 1 m {100 * (d < 1).mean():.0f}%")
print("the best skyline cell, whatever the points say:")
show(rows[0])
for lam in (0.5, 1.0, 2.0):
    print(f"the best by skyline + {lam} x points median:")
    for r in sorted(rows, key=lambda r: r["skyline"] + lam * r["points_median_m"])[:4]:
        show(r)
best = min(rows, key=lambda r: r["skyline"] + r["points_median_m"])
q = np.array(best["move"])
th = np.radians(q[1])
pl["t"] = put(np.array(pl["t"]), q).tolist()   # X' = pivot + sc Q (X - pivot) + shift, as skyline_refit_try.py
pl["yaw"], pl["scale"] = pl["yaw"] - th, pl["scale"] * q[0]
pl["skyline_and_points"] = dict(pivot=pivot.tolist(), fit=fit_ids, **best)
json.dump(pl, open(out / "placement_combined.json", "w"), indent=1)
print("saved combined.json, placement_combined.json")
