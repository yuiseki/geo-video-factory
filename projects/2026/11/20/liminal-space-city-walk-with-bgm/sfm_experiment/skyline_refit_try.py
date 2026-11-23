"""skyline_refit_try.py <photos.npz> <model_grid.npz> <out_dir> <fit ids> <test ids> [result.json of the search] [placement.json]
Experiment: the single-photo search of skyline_match_try.py puts its winners 15 to 23 m from the poses of the
placement, all to the same side. Is the placement what is off? Move the cameras together (one turn about the
vertical and one scale about their centre, one shift) and add up the skyline costs of the photos listed in
<fit ids> (comma separated, the last three digits of the names). The move is then read on <test ids>, which
took no part in the fit. Standing points are snapped to the grid of model_grid.npz (as coarse as that grid).
With result.json, the errors of the single-photo winners are counted again from the moved poses.
With placement.json (the one the photos were posed with), the move is folded into it and written as
placement_moved.json, in the same fields. The roofline says little about the scale, so refit that one to the
SfM points afterwards (place_tilt_try.py with the tilts 0 0)."""
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import skyline_match as sm  # noqa: E402

ph = np.load(sys.argv[1])
z = np.load(sys.argv[2])
out = Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
fit_ids, test_ids = sys.argv[4].split(","), sys.argv[5].split(",")
names = [str(n)[-7:-4] for n in ph["names"]]
eyes, BINS, TAU = ph["eyes"], int(ph["bins"]), 5.0
photos = [dict(sky=ph["sky"][i], floor=ph["floor"][i], ceil=ph["ceil"][i]) for i in range(len(names))]
places = z["places"]
xs, ys, zs = np.unique(places[:, 0]), np.unique(places[:, 1]), np.unique(places[:, 2])
G = z["skyline"].reshape(len(zs), len(ys), len(xs), BINS)
pivot = eyes.mean(0)

SCALES = np.arange(0.80, 1.4001, 0.025)
TURNS = np.arange(-24, 13)                     # in bins: half degrees
DX, DY, DZ = np.arange(-14, 15, 2.0), np.arange(-36, 13, 2.0), np.array([-4.5, -3.0, -1.5, 0.0, 1.5])


def moved(i, scale, turn_bins):
    """Where photo i stands after the scale and the turn (clockwise, in bins) about the pivot."""
    th = np.radians(turn_bins * 360 / BINS)
    Q = np.array([[np.cos(th), np.sin(th), 0], [-np.sin(th), np.cos(th), 0], [0, 0, 1]])
    return pivot + scale * (eyes[i] - pivot) @ Q.T


def costs(i, scale, turn_bins):
    """The cost of photo i for every shift (dz, dy, dx); inf where the grid does not reach."""
    e = moved(i, scale, turn_bins)
    ix = np.round((e[0] + DX - xs[0]) / (xs[1] - xs[0])).astype(int)
    iy = np.round((e[1] + DY - ys[0]) / (ys[1] - ys[0])).astype(int)
    iz = np.round((e[2] + DZ - zs[0]) / (zs[1] - zs[0])).astype(int)
    ok = (((iz >= 0) & (iz < len(zs)))[:, None, None] & ((iy >= 0) & (iy < len(ys)))[None, :, None]
          & ((ix >= 0) & (ix < len(xs)))[None, None, :])
    sub = G[np.clip(iz, 0, len(zs) - 1)][:, np.clip(iy, 0, len(ys) - 1)][:, :, np.clip(ix, 0, len(xs) - 1)]
    c = sm.match_cost(photos[i], sub.reshape(-1, BINS), tau=TAU, shifts=[turn_bins % BINS]).reshape(ok.shape)
    return np.where(ok, c, np.inf)


fit = [names.index(n) for n in fit_ids]
test = [names.index(n) for n in test_ids]
J = np.full((len(SCALES), len(TURNS), len(DZ), len(DY), len(DX)), np.inf)
for a, sc in enumerate(SCALES):
    for b, tb in enumerate(TURNS):
        J[a, b] = np.mean([costs(i, sc, tb) for i in fit], axis=0)
best = np.unravel_index(np.argmin(J), J.shape)
sc, tb = SCALES[best[0]], TURNS[best[1]]
shift = np.array([DX[best[4]], DY[best[3]], DZ[best[2]]])
zero = (int(np.argmin(np.abs(SCALES - 1))), int(np.argmin(np.abs(TURNS))), int(np.argmin(np.abs(DZ))),
        int(np.argmin(np.abs(DY))), int(np.argmin(np.abs(DX))))
print(f"fit on {fit_ids}: scale x{sc:.3f}, turn {tb * 360 / BINS:+.1f} deg, shift east {shift[0]:+.0f} m north {shift[1]:+.0f} m "
      f"up {shift[2]:+.1f} m; cost {J[zero]:.3f} as placed -> {J[best]:.3f}", flush=True)
flat = np.argsort(J.ravel())[:10]
print("the ten best moves (scale, turn deg, up, north, east, cost):")
for k in flat:
    q = np.unravel_index(k, J.shape)
    print(f"  x{SCALES[q[0]]:.3f} {TURNS[q[1]] * 360 / BINS:+5.1f}  {DZ[q[2]]:+4.1f} {DY[q[3]]:+4.0f} {DX[q[4]]:+4.0f}  {J[q]:.3f}")


def read(ids, tag):
    rows = []
    for i in ids:
        before = costs(i, 1.0, 0)[zero[2], zero[3], zero[4]]
        after = costs(i, sc, tb)[best[2], best[3], best[4]]
        rows.append(dict(name=names[i], as_placed=float(before), moved=float(after)))
        print(f"  {tag} {names[i]}  as placed {before:.2f}  moved {after:.2f}")
    print(f"  {tag} mean: as placed {np.mean([r['as_placed'] for r in rows]):.3f}  moved {np.mean([r['moved'] for r in rows]):.3f}", flush=True)
    return rows


res = dict(pivot=pivot.tolist(), scale=float(sc), turn_deg=float(tb * 360 / BINS), shift=shift.tolist(),
           cost_as_placed=float(J[zero]), cost_moved=float(J[best]), fit=read(fit, "fit "), test=read(test, "test"))
new_eyes = np.array([moved(i, sc, tb) for i in range(len(names))]) + shift
res["eyes"] = {n: e.tolist() for n, e in zip(names, new_eyes)}
print(f"cameras after the move: {np.median(new_eyes[:, 2]) - float(ph['ground']):.2f} m above the ground", flush=True)

if len(sys.argv) > 6:
    found = {str(p["name"])[-7:-4]: p for p in json.load(open(sys.argv[6]))["photos"]}
    again = []
    for n, e in zip(names, new_eyes):
        p = found[n]
        d = np.array(p["found"]) - e
        again.append(dict(name=n, error_m=float(np.hypot(d[0], d[1])), error_z_m=float(d[2]),
                          error_turn_deg=float(p["error_turn_deg"] - tb * 360 / BINS), sky_bins=p["bins"]["sky"]))
    res["single_photo_search_again"] = again
    for lo, tag in ((100, "100 or more roofline bins"), (0, "all")):
        err = np.array([r["error_m"] for r in again if r["sky_bins"] >= lo and r["name"] <= "025"])
        tn = np.abs([r["error_turn_deg"] for r in again if r["sky_bins"] >= lo and r["name"] <= "025"])
        print(f"single-photo winners against the moved poses, photos 001-025, {tag}: {len(err)} photos, median {np.median(err):.1f} m, "
              f"within 5 m {int((err <= 5).sum())}, within 10 m {int((err <= 10).sum())}, turn within 3 deg {int((tn <= 3).sum())}")
json.dump(res, open(out / "refit.json", "w"), indent=1)

if len(sys.argv) > 7:
    pl = json.load(open(sys.argv[7]))
    th = np.radians(res["turn_deg"])
    Q = np.array([[np.cos(th), np.sin(th), 0], [-np.sin(th), np.cos(th), 0], [0, 0, 1]])  # clockwise by the turn
    pl["t"] = (pivot + sc * (np.array(pl["t"]) - pivot) @ Q.T + shift).tolist()            # X' = pivot + sc Q (X - pivot) + shift
    pl["yaw"], pl["scale"] = pl["yaw"] - th, pl["scale"] * sc
    pl["skyline_refit"] = {k: res[k] for k in ("pivot", "scale", "turn_deg", "shift", "cost_as_placed", "cost_moved")}
    json.dump(pl, open(out / "placement_moved.json", "w"), indent=1)

fig, ax = plt.subplots(1, 3, figsize=(16, 4.8), dpi=90)
ax[0].plot(SCALES, J.min(axis=(1, 2, 3, 4)), "o-"); ax[0].set_xlabel("scale about the cameras' centre"); ax[0].set_ylabel("mean cost of the fitted photos (best over the rest)")
ax[1].plot(TURNS * 360 / BINS, J.min(axis=(0, 2, 3, 4)), "o-"); ax[1].set_xlabel("turn about the vertical (deg, clockwise)")
im = ax[2].imshow(J.min(axis=(0, 1, 2)), origin="lower", extent=(DX[0] - 1, DX[-1] + 1, DY[0] - 1, DY[-1] + 1), cmap="viridis_r")
ax[2].plot(0, 0, "o", mfc="none", mec="red", ms=10); ax[2].set_xlabel("shift east (m)"); ax[2].set_ylabel("shift north (m)")
fig.colorbar(im, ax=ax[2])
for a in ax[:2]:
    a.grid(alpha=.3)
fig.tight_layout(); fig.savefig(out / "refit.png")
print("saved refit.json, refit.png")
