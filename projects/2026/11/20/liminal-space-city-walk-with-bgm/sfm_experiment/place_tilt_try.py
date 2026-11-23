"""place_tilt_try.py <sparse_model_dir> <placement.json of place_on_plateau.py> <plateau tris.npz> <out_prefix>
                     [<tilt about east, deg> <tilt about north, deg>]
Experiment: place_on_plateau.py keeps the up axis of place_on_footprints.py (the common normal of the cameras'
right axes and of the spread of their positions). When the cameras stand in a row along one wall, a rotation
about the direction of that wall is only weakly fixed that way. Free the two tilt angles (about east and about
north, around the cameras' centre), fit them to the PLATEAU surfaces together with yaw, scale and shift, and
see (1) how the cost changes along each tilt and (2) where the cameras end up above the ground.
Writes <out_prefix>.json in the format of place_on_plateau.py (the tilt is folded into basis, centroid,
z_cam_median and t), so the other scripts read it unchanged.
With the two angles given (for example from the vertical vanishing points of the photos), nothing is searched
along the tilt: that tilt is applied about the cameras' centre and three placements are written, <out_prefix>
_asgiven.json (nothing refitted), _shift.json (shift refitted) and _all.json (yaw, scale and shift refitted).
The fit to PLATEAU has many local minima (see the profile), so compare the three instead of trusting the last."""
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
B = np.array(pl["basis"])
o = np.array([*pl["centroid"], pl["z_cam_median"]])
C = np.array([im.projection_center() for im in rec.images.values()]) @ B.T - o
P = np.array([p.xyz for p in rec.points3D.values()]) @ B.T - o

# the same surface samples and the same points as place_on_plateau.py (same seed, same order of draws)
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
ground = pl["ground"]
use = P[P[:, 2] * pl["scale"] > 3]
use = use[rng.choice(len(use), min(4000, len(use)), replace=False)]
KEEP = 0.7


def rot(yaw, ax, ay):
    """tilt (about east by ax, about north by ay) applied after the yaw about up"""
    c, s = np.cos(yaw), np.sin(yaw)
    A = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    c, s = np.cos(ax), np.sin(ax)
    Rx = np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    c, s = np.cos(ay), np.sin(ay)
    Ry = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return Rx @ Ry @ A


def place(X, q):
    """q = yaw, log scale, tx, ty, tz, ax, ay. t is where the model's origin (the cameras' centre) lands."""
    return np.exp(q[1]) * X @ rot(q[0], q[5], q[6]).T + q[2:5]


def cost(q):
    d = tree.query(place(use, q), distance_upper_bound=30.0)[0]
    return np.sort(np.minimum(d, 30.0))[:int(KEEP * len(use))].mean() / np.exp(q[1])


def fit(q0, free):
    """Nelder-Mead over the parameters listed in free, the others stay at q0"""
    q0 = np.array(q0, float)
    step = np.array([np.radians(2), 0.03, 2, 2, 2, np.radians(1.5), np.radians(1.5)])

    def full(x):
        q = q0.copy(); q[free] = x
        return q
    x0 = q0[free]
    simplex = np.vstack([x0, x0 + np.diag(step[free])])
    r = optimize.minimize(lambda x: cost(full(x)), x0, method="Nelder-Mead",
                          options=dict(xatol=1e-4, fatol=1e-7, maxiter=4000, initial_simplex=simplex))
    r = optimize.minimize(lambda x: cost(full(x)), r.x, method="Nelder-Mead",
                          options=dict(xatol=1e-4, fatol=1e-7, maxiter=4000,
                                       initial_simplex=np.vstack([r.x, r.x + np.diag(step[free] * 0.3)])))
    return full(r.x), float(r.fun)


def describe(tag, q):
    d = tree.query(place(use, q))[0]
    Cw = place(C, q)
    h = Cw[:, 2] - ground
    print(f"{tag}: scale {np.exp(q[1]):.3f}  cost {cost(q):.4f}  median {np.median(d):.2f} m  within 1 m "
          f"{100 * (d < 1).mean():.0f}%  tilt about east {np.degrees(q[5]):+.2f} deg, about north {np.degrees(q[6]):+.2f} deg  "
          f"cameras {np.median(h):.2f} m above the ground (from {h.min():.2f} to {h.max():.2f})", flush=True)
    return dict(scale=float(np.exp(q[1])), cost=cost(q), median_m=float(np.median(d)), within_1m=float((d < 1).mean()),
                tilt_east_deg=float(np.degrees(q[5])), tilt_north_deg=float(np.degrees(q[6])),
                eye_above_ground=[float(np.median(h)), float(h.min()), float(h.max())], yaw=float(q[0]))


def fold(q, note):
    """the placement q in the fields the other scripts read: X_w = s A (B' X - o') + t'"""
    A = rot(q[0], 0, 0)
    T = rot(q[0], q[5], q[6]) @ A.T
    Bn = A.T @ T @ A @ B
    on = A.T @ T @ A @ o
    check = np.exp(q[1]) * (C[:3] + o) @ np.linalg.inv(B).T @ Bn.T @ A.T - np.exp(q[1]) * on @ A.T + q[2:5]
    assert np.allclose(check, place(C[:3], q), atol=1e-6), "the folded form does not reproduce the placement"
    return dict(origin=pl["origin"], basis=Bn.tolist(), centroid=on[:2].tolist(), z_cam_median=float(on[2]),
                yaw=float(q[0]), scale=float(np.exp(q[1])), t=[float(x) for x in q[2:5]],
                ground=float(ground), tilt_try=note)


# the placement as given: the same formula as place_on_plateau.py (its t already holds the shift)
q_in = np.array([pl["yaw"], np.log(pl["scale"]), *pl["t"], 0.0, 0.0])
out = dict(input=describe("as given       ", q_in))
if len(sys.argv) > 6:
    q_tilt = q_in.copy(); q_tilt[5:7] = np.radians([float(sys.argv[5]), float(sys.argv[6])])
    for tag, free in (("asgiven", []), ("shift", [2, 3, 4]), ("all", [0, 1, 2, 3, 4])):
        q = fit(q_tilt, free)[0] if free else q_tilt
        note = dict(out, fixed_tilt=describe(f"tilt, {tag:8s}", q), refitted=tag)
        json.dump(fold(q, note), open(f"{prefix}_{tag}.json", "w"), indent=1)
    sys.exit(0)
q_flat, _ = fit(q_in, [0, 1, 2, 3, 4])
out["refit_without_tilt"] = describe("refit, no tilt ", q_flat)
q_free, _ = fit(q_flat, [0, 1, 2, 3, 4, 5, 6])
out["refit_with_tilt"] = describe("refit with tilt", q_free)

# the cost along each tilt, everything else refitted at each step
prof = {}
for k, name in ((5, "east"), (6, "north")):
    rows = []
    for deg in np.arange(-8, 8.01, 1.0):
        q0 = q_free.copy(); q0[k] = np.radians(deg)
        q, c = fit(q0, [i for i in range(7) if i != k])
        h = np.median(place(C, q)[:, 2]) - ground
        rows.append(dict(deg=float(deg), cost=c, scale=float(np.exp(q[1])), eye_above_ground=float(h)))
        print(f"tilt about {name:5s} {deg:+5.1f} deg  cost {c:.4f}  scale {np.exp(q[1]):.3f}  cameras {h:5.2f} m", flush=True)
    prof[name] = rows
out["profile"] = prof

json.dump(fold(q_free, out), open(prefix + ".json", "w"), indent=1)

fig, ax = plt.subplots(1, 2, figsize=(14, 5.5), dpi=100)
for a, name in zip(ax, ("east", "north")):
    rows = prof[name]
    a.plot([r["deg"] for r in rows], [r["cost"] for r in rows], "o-", color="#1f77b4")
    a.axvline(out["refit_with_tilt"][f"tilt_{name}_deg"], color="#d62728", lw=0.8)
    a.set_xlabel(f"tilt about {name} (deg); everything else refitted"); a.set_ylabel("trimmed mean distance to PLATEAU (model units)")
    a.grid(alpha=.3)
    b = a.twinx(); b.plot([r["deg"] for r in rows], [r["eye_above_ground"] for r in rows], "s--", color="#888", ms=3)
    b.set_ylabel("cameras above the PLATEAU ground (m), grey")
fig.tight_layout(); fig.savefig(prefix + ".png"); print("saved", prefix + ".png")
