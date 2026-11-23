"""place_on_footprints.py <sparse_model_dir> <images_dir> <overpass buildings.json (out geom)> <name substring> <out_prefix>
Experiment: put a COLMAP model of ONE building on the map from the photos' EXIF GPS and the building's outline.
1. up: the direction most perpendicular to the cameras' right axes and to the spread of the camera
   centres (hand-held on flat ground). The mean of the cameras' down axes is biased when the photos look up.
2. GPS gives only the rough place of the cameras (phone GPS between tall buildings: 10 m and worse), and
   a rough scale. Heading comes from the outline: search yaw x scale x shift so that the model's wall points
   (top view) lie on the outline of the named building, the cameras stay outside every building and near
   their GPS centroid. The cost is in model units (metres / scale), so shrinking the model is not rewarded.
Writes <out_prefix>.json and <out_prefix>.png, prints the best solutions."""
import zlib  # noqa: F401  (before pycolmap)
import json
import sys
from pathlib import Path

import numpy as np
import pycolmap
from PIL import Image, ImageDraw
from scipy import ndimage, optimize
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rec = pycolmap.Reconstruction(sys.argv[1])
img_dir, name_part, prefix = Path(sys.argv[2]), sys.argv[4], sys.argv[5]


def gps(p):
    g = Image.open(p).getexif().get_ifd(0x8825)
    d = lambda v, r: (float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600) * (-1 if r in "SW" else 1)
    return d(g[4], g[3]), d(g[2], g[1])


names, C, RIGHT, DOWN, G = [], [], [], [], []
for im in rec.images.values():
    R = im.cam_from_world().rotation.matrix()
    names.append(im.name); C.append(im.projection_center()); RIGHT.append(R[0]); DOWN.append(R[1])
    G.append(gps(img_dir / im.name))
C, RIGHT, G = np.array(C), np.array(RIGHT), np.array(G)
Cc = C - C.mean(0)
A = np.vstack([RIGHT, Cc / np.sqrt((Cc ** 2).sum(1).mean())])
up = np.linalg.svd(A)[2][-1]
if up @ np.mean(DOWN, 0) > 0:
    up = -up
tilt = np.degrees(np.arccos(np.clip(-up @ (np.mean(DOWN, 0) / np.linalg.norm(np.mean(DOWN, 0))), -1, 1)))
a = np.cross(up, [1.0, 0, 0]); a /= np.linalg.norm(a); b = np.cross(up, a)
B = np.stack([a, b, up])                                   # right-handed, z up
P = np.array([p.xyz for p in rec.points3D.values()]); col = np.array([p.color for p in rec.points3D.values()]) / 255
Pg, Cg = P @ B.T, C @ B.T
Pg[:, 2] -= np.median(Cg[:, 2]); Cg[:, 2] -= np.median(Cg[:, 2])

lon0, lat0 = G.mean(0)
kn = 6378137.0 * np.pi / 180; ke = kn * np.cos(np.radians(lat0))
E = np.c_[(G[:, 0] - lon0) * ke, (G[:, 1] - lat0) * kn]
gps_scale = np.sqrt((E - E.mean(0)).var(0).sum() / (Cg[:, :2] - Cg[:, :2].mean(0)).var(0).sum())

# --- map rasters, 0.5 m cells
doc = json.load(open(sys.argv[3]))
polys = [(np.array([((g["lon"] - lon0) * ke, (g["lat"] - lat0) * kn) for g in e["geometry"]]), e.get("tags", {}))
         for e in doc["elements"] if "geometry" in e]
target = [(xy, t) for xy, t in polys if name_part in t.get("name", "")]
assert len(target) == 1, [t.get("name") for _, t in target]
CELL, HALF = 0.5, 260.0
n = int(2 * HALF / CELL)
to_px = lambda xy: np.c_[(xy[:, 0] + HALF) / CELL, (HALF - xy[:, 1]) / CELL]
im_out, im_in = Image.new("L", (n, n), 0), Image.new("L", (n, n), 0)
ImageDraw.Draw(im_out).line([tuple(v) for v in to_px(target[0][0])], fill=255, width=1)
for xy, _ in polys:
    ImageDraw.Draw(im_in).polygon([tuple(v) for v in to_px(xy)], fill=255)
dist = ndimage.distance_transform_edt(np.array(im_out) == 0) * CELL     # metres to the target outline
inside = ndimage.binary_erosion(np.array(im_in) > 0, iterations=4)      # 2 m inside any building


def look(arr, xy, fill):
    px = np.round(to_px(xy)).astype(int)
    ok = (px[:, 0] >= 0) & (px[:, 0] < n) & (px[:, 1] >= 0) & (px[:, 1] < n)
    out = np.full(len(xy), fill, arr.dtype)
    out[ok] = arr[px[ok, 1], px[ok, 0]]
    return out


h = Pg[:, 2] * gps_scale
wall = Pg[(h > 4) & (h < 80)][:, :2]
rng = np.random.default_rng(0)
wall = wall[rng.choice(len(wall), min(1500, len(wall)), replace=False)]
c0 = Cg[:, :2].mean(0)
KEEP = 0.7


def place(xy, yaw, s, t):
    c, sn = np.cos(yaw), np.sin(yaw)
    return s * (xy - c0) @ np.array([[c, sn], [-sn, c]]) + t          # t = where the camera centroid lands


def cost(yaw, s, t):
    d = np.sort(look(dist, place(wall, yaw, s, t), 99.0))[:int(KEEP * len(wall))].mean() / s
    cams_in = look(inside, place(Cg[:, :2], yaw, s, t), False).mean()
    far = max(0.0, np.hypot(*t) - 25.0) / s
    return d + 5.0 * cams_in / s * 10 + far


shifts = np.array([(x, y) for x in np.arange(-25, 26, 5.0) for y in np.arange(-25, 26, 5.0) if np.hypot(x, y) <= 25])
rows = []
for yaw in np.radians(np.arange(0, 360, 3)):
    for s in gps_scale * np.geomspace(0.4, 2.5, 20):
        rows += [(cost(yaw, s, t), yaw, s, *t) for t in shifts]
rows.sort()
sols = []
for c, yaw, s, tx, ty in rows:
    if all(abs((yaw - q["yaw"] + np.pi) % (2 * np.pi) - np.pi) > np.radians(15) or abs(np.log(s / q["s"])) > 0.25 or
           np.hypot(tx - q["t"][0], ty - q["t"][1]) > 12 for q in sols):
        r = optimize.minimize(lambda v: cost(v[0], np.exp(v[1]), v[2:]), [yaw, np.log(s), tx, ty], method="Nelder-Mead",
                              options=dict(xatol=1e-3, fatol=1e-4, maxiter=600))
        sols.append(dict(cost=float(r.fun), yaw=float(r.x[0]), s=float(np.exp(r.x[1])), t=[float(r.x[2]), float(r.x[3])],
                         coarse=float(c)))
    if len(sols) == 5:
        break
sols.sort(key=lambda q: q["cost"])
print(f"{len(names)} cameras, {len(P)} points, {len(wall)} wall points; up differs from the mean down axis by {tilt:.1f} deg; "
      f"scale from GPS {gps_scale:.2f} m/unit")
for q in sols:
    d = look(dist, place(wall, q["yaw"], q["s"], q["t"]), 99.0)
    q["wall_median_m"] = float(np.median(d)); q["wall_within_2m"] = float((d < 2).mean())
    q["facade_top_m"] = float(np.percentile(Pg[(h > 4) & (look(dist, place(Pg[:, :2], q["yaw"], q["s"], q["t"]), 99.0) < 3), 2], 98) * q["s"])
    q["gps_residual_median_m"] = float(np.median(np.linalg.norm(place(Cg[:, :2], q["yaw"], q["s"], q["t"]) - E, axis=1)))
    print(f"cost {q['cost']:.3f} (model units)  yaw {np.degrees(q['yaw']) % 360:5.1f}  scale {q['s']:.2f} m/unit  "
          f"cameras moved {np.hypot(*q['t']):4.1f} m from the GPS centroid  wall median {q['wall_median_m']:.1f} m, "
          f"{100 * q['wall_within_2m']:.0f}% within 2 m  facade top {q['facade_top_m']:.1f} m above the cameras  "
          f"GPS residual median {q['gps_residual_median_m']:.1f} m")
json.dump(dict(origin=[lon0, lat0], up=up.tolist(), basis=B.tolist(), centroid=c0.tolist(), gps_scale=float(gps_scale),
               target_tags=target[0][1], solutions=sols), open(prefix + ".json", "w"), indent=1, ensure_ascii=False)

fig, ax = plt.subplots(1, 3, figsize=(21, 8), dpi=100, gridspec_kw=dict(width_ratios=[1, 1, 1.1]))
for k, q in enumerate(sols[:2]):
    pe, ce = place(Pg[:, :2], q["yaw"], q["s"], q["t"]), place(Cg[:, :2], q["yaw"], q["s"], q["t"])
    for xy, t in polys:
        tg = name_part in t.get("name", "")
        ax[k].plot(xy[:, 0], xy[:, 1], "-", color="#111" if tg else "#999", lw=1.8 if tg else 0.6, zorder=2)
    ax[k].scatter(pe[:, 0], pe[:, 1], s=1.5, c=col, linewidths=0, zorder=3)
    ax[k].scatter(E[:, 0], E[:, 1], s=30, facecolors="none", edgecolors="#1f77b4", zorder=4, label="EXIF GPS")
    ax[k].scatter(ce[:, 0], ce[:, 1], s=12, color="#d62728", zorder=5, label="cameras (SfM)")
    ax[k].set_xlim(-120, 130); ax[k].set_ylim(-140, 110); ax[k].set_aspect("equal"); ax[k].grid(alpha=.3); ax[k].set_facecolor("#f4f4f4")
    ax[k].set_title(f"solution {k + 1}: cost {q['cost']:.3f}, scale {q['s']:.2f} m/unit, {100 * q['wall_within_2m']:.0f}% of wall points within 2 m")
    ax[k].legend(loc="lower left")
q = sols[0]
pe = place(Pg[:, :2], q["yaw"], q["s"], q["t"])
near = look(dist, pe, 99.0) < 4
ax[2].scatter(pe[near, 1], Pg[near, 2] * q["s"], s=2, c=col[near], linewidths=0)
ax[2].axhline(0, color="#d62728", lw=0.8); ax[2].set_aspect("equal"); ax[2].grid(alpha=.3); ax[2].set_facecolor("#f4f4f4")
ax[2].set_title("solution 1, points within 4 m of the outline: north (m) x height above the cameras (m)")
fig.tight_layout(); fig.savefig(prefix + ".png"); print("saved", prefix + ".png")
