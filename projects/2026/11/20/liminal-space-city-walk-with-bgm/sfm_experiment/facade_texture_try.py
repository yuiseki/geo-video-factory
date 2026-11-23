"""facade_texture_try.py <sparse_model_dir> <images_dir> <placement.json of place_on_plateau.py>
                         <overpass buildings.json (out geom)> <name substring> <out_dir> [texel_m=0.05] [upright|lean|relief]
Experiment: geometry-guided facade texturing. The wall is not found in the photos; it is taken from the
OpenStreetMap outline of the named building (moved onto the reconstruction's wall points) and the PLATEAU
ground height. Every texel of that wall is projected into every registered photo and the views are fused
(packages/pipeline/facade_ortho.py). Writes the median and best-view textures, how many photos saw each
texel, how much they disagree, a plan of the guide and a few single views. Nothing handles occlusion yet."""
import zlib  # noqa: F401
import json
import sys
from pathlib import Path

import numpy as np
import pycolmap
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import facade_ortho as fo  # noqa: E402

model, images, placement, osm, name, out = sys.argv[1:7]
STEP = float(sys.argv[7]) if len(sys.argv) > 7 else 0.05
SHAPE = sys.argv[8] if len(sys.argv) > 8 else "upright"  # upright: a vertical wall; lean: tilted as the points are;
assert SHAPE in ("upright", "lean", "relief"), SHAPE      # relief: moved onto the points cell by cell (set-backs)
CELL_S, CELL_Z = 3.0, 4.0
BELOW, ABOVE = 3.0, 57.0                  # metres of wall below and above the PLATEAU ground
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
Image.MAX_IMAGE_PIXELS = None

pl = json.load(open(placement))
B, c0, zc = np.array(pl["basis"]), np.array(pl["centroid"]), pl["z_cam_median"]
yaw, s, t, ground = pl["yaw"], pl["scale"], np.array(pl["t"]), pl["ground"]
lon0, lat0 = pl["origin"]
assert abs(np.linalg.det(B) - 1) < 1e-6, "the basis mirrors the model"

# model -> world (metres, z up): X_w = s * A @ (B @ X - o) + t
c, sn = np.cos(yaw), np.sin(yaw)
A = np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1]])
o = np.array([c0[0], c0[1], zc])


def to_world(X):
    return s * (X @ B.T - o) @ A.T + t


rec = pycolmap.Reconstruction(model)
P = to_world(np.array([p.xyz for p in rec.points3D.values()]))
views = []
for im in sorted(rec.images.values(), key=lambda im: im.name):
    cam = rec.cameras[im.camera_id]
    assert "SIMPLE_RADIAL" in str(cam.model), cam.model
    T = im.cam_from_world()
    Rc, tc = T.rotation.matrix(), np.array(T.translation)
    R = Rc @ B.T @ A.T                                   # world -> camera, depth in metres
    views.append(dict(name=im.name, R=R, t=-R @ t + s * (Rc @ B.T @ o + tc), params=list(map(float, cam.params))))
eyes = np.array([-v["R"].T @ v["t"] for v in views])
print(f"{len(views)} photos, {len(P)} points; cameras {np.median(eyes[:, 2]) - ground:.1f} m above the PLATEAU ground")

# the guide: the OSM outline, counter-clockwise, starting at the vertex farthest from the cameras
kn = 6378137.0 * np.pi / 180
ke = kn * np.cos(np.radians(lat0))
el = [e for e in json.load(open(osm))["elements"] if name in e.get("tags", {}).get("name", "") and "geometry" in e]
assert len(el) == 1, [e["id"] for e in el]
ring = np.array([((g["lon"] - lon0) * ke, (g["lat"] - lat0) * kn) for g in el[0]["geometry"]])[:-1]
x, y = ring[:, 0], ring[:, 1]
if np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) < 0:
    ring = ring[::-1]
ring = np.roll(ring, -int(np.argmax(np.linalg.norm(ring - eyes[:, :2].mean(0), axis=1))), axis=0)
ring = np.vstack([ring, ring[:1]])

wall = P[(P[:, 2] > ground + 3) & (P[:, 2] < ground + ABOVE)]
FIT = 0.5
line, offset, count = fo.fit_curtain(ring, wall[:, :2], step=FIT, reach=6.0)
i0, i1 = fo.covered_run(count, min_points=10, max_gap=int(6 / FIT))
used = line[i0:i1 + 1]
print(f"OSM way {el[0]['id']}: outline {len(count) * FIT:.0f} m, covered by points {(i1 - i0 + 1) * FIT:.0f} m; "
      f"the points are {np.median(offset[i0:i1 + 1]):+.2f} m outside the outline (median), "
      f"{offset[i0:i1 + 1].min():+.2f} to {offset[i0:i1 + 1].max():+.2f}")

# does the wall stand upright in this frame? distance of the points outside the fitted line, by height
u_xy, u_d, _ = fo.resample(used, FIT)
u_n = np.c_[u_d[:, 1], -u_d[:, 0]]
j = np.argmin(((wall[:, None, :2] - u_xy[None]) ** 2).sum(-1), axis=1)
rel = wall[:, :2] - u_xy[j]
dn, da = (rel * u_n[j]).sum(1), (rel * u_d[j]).sum(1)
keep = (np.abs(dn) < 6) & (np.abs(da) < FIT)
hz, dn = wall[keep, 2] - ground, dn[keep]
for lo in range(0, int(ABOVE), 6):
    b = (hz >= lo) & (hz < lo + 6)
    if b.sum() >= 20:
        print(f"  {lo:2d}-{lo + 6:2d} m: {b.sum():5d} points, {np.median(dn[b]):+.2f} m outside the line")
slopes = [(dn[b] - dn[a]) / (hz[b] - hz[a]) for a, b in np.random.default_rng(0).integers(0, len(hz), (20000, 2))
          if abs(hz[b] - hz[a]) > 5]
lean = float(np.median(slopes))                          # Theil-Sen
z_mid = float(np.median(hz))
print(f"lean {lean:+.4f} m per m ({np.degrees(np.arctan(lean)):+.2f} deg, positive = the top hangs outwards), "
      f"about the height {z_mid:.1f} m; shape: {SHAPE}")

pts, normals, arc = fo.curtain(used, ground - BELOW, BELOW + ABOVE, STEP)
if SHAPE == "lean":
    pts[..., :2] += (lean * (pts[..., 2] - ground - z_mid))[..., None] * normals[None]
if SHAPE == "relief":
    relief, cells = fo.fit_relief(used, P, ground - BELOW, BELOW + ABOVE, CELL_S, CELL_Z, reach=8.0)
    pts = fo.apply_relief(pts, normals, relief, CELL_S, CELL_Z, STEP)
    print(f"relief: {(cells >= 8).mean() * 100:.0f}% of the {relief.shape[1]} x {relief.shape[0]} cells have points; "
          f"offsets {relief.min():+.1f} to {relief.max():+.1f} m")
rows, cols = pts.shape[:2]
print(f"texture {cols} x {rows} at {STEP * 100:.0f} cm per texel")
stack = np.zeros((len(views), rows, cols, 3), np.uint8)
valid = np.zeros((len(views), rows, cols), bool)
score = np.zeros((len(views), rows, cols), np.float32)
for i, v in enumerate(views):
    img = np.asarray(Image.open(Path(images) / v["name"]).convert("RGB"))
    stack[i], valid[i], score[i] = fo.ortho_view(img, pts, normals, v["R"], v["t"], *v["params"])
    print(f"  {v['name']}: sees {100 * valid[i].mean():4.1f}% of the wall, up to {score[i].max():5.1f} px/m", flush=True)

median, seen = fo.fuse_median(stack, valid)
best, which = fo.fuse_best(stack, score)
Image.fromarray(median).save(out / "median.png")
Image.fromarray(best).save(out / "best.png")

# disagreement between the views of a texel: median absolute difference from the fused colour (grey levels)
grey = stack.astype(np.float32).mean(-1)
dev = np.full((rows, cols), np.nan, np.float32)
for r0 in range(0, rows, 64):
    g = np.where(valid[:, r0:r0 + 64], np.abs(grey[:, r0:r0 + 64] - median[r0:r0 + 64].astype(np.float32).mean(-1)), np.nan)
    enough = seen[r0:r0 + 64] >= 3
    if enough.any():
        dev[r0:r0 + 64][enough] = np.nanmedian(g[:, enough], axis=0)
stats = dict(way=el[0]["id"], texel_m=STEP, cols=cols, rows=rows, length_m=cols * STEP, z_bottom=ground - BELOW,
             z_top=ground + ABOVE, lean_m_per_m=lean, shape=SHAPE, offset_median_m=float(np.median(offset[i0:i1 + 1])),
             seen_by_any=float((seen > 0).mean()), seen_by_3=float((seen >= 3).mean()),
             views_median=float(np.median(seen[seen > 0])), deviation_median=float(np.nanmedian(dev)),
             deviation_p90=float(np.nanpercentile(dev, 90)), best_px_per_m_median=float(np.median(score.max(0)[seen > 0])))
json.dump(dict(stats=stats, polyline=used.tolist(), views=[v["name"] for v in views]), open(out / "facade.json", "w"), indent=1)
print(json.dumps(stats, indent=1))

extent = [0, cols * STEP, -BELOW, ABOVE]
fig, ax = plt.subplots(4, 1, figsize=(16, 4 * 16 * rows / cols + 3), constrained_layout=True)
ax[0].imshow(median, extent=extent)
ax[0].set_title(f"median of the views that saw each texel ({cols} x {rows}, {STEP * 100:.0f} cm per texel)", loc="left")
ax[1].imshow(best, extent=extent)
ax[1].set_title("each texel from the view with the most pixels per metre", loc="left")
m = ax[2].imshow(np.where(seen > 0, seen, np.nan), extent=extent, cmap="Blues", vmin=0, vmax=len(views))
fig.colorbar(m, ax=ax[2], label="photos", shrink=0.8)
ax[2].set_title("how many photos saw each texel", loc="left")
m = ax[3].imshow(dev, extent=extent, cmap="Blues", vmin=0, vmax=40)
fig.colorbar(m, ax=ax[3], label="grey levels", shrink=0.8)
ax[3].set_title("disagreement: median absolute difference of the views from the fused colour (3 photos or more)", loc="left")
for a in ax:
    a.set_ylabel("m above the PLATEAU ground")
    a.axhline(0, color="#888", lw=0.6)
ax[3].set_xlabel("m along the wall, left to right as seen from outside")
fig.savefig(out / "facade.png", dpi=110)

fig, ax = plt.subplots(figsize=(9, 9), constrained_layout=True)
near = P[(np.abs(P[:, 0] - used[:, 0].mean()) < 150) & (np.abs(P[:, 1] - used[:, 1].mean()) < 150)]
ax.plot(near[:, 0], near[:, 1], ",", color="#9aa", zorder=1)
ax.plot(ring[:, 0], ring[:, 1], "-", color="#111", lw=1.0, label="OSM outline (guide)", zorder=3)
ax.plot(used[:, 0], used[:, 1], "-", color="#2a78d6", lw=2.5, label="wall that is textured (guide moved onto the points)", zorder=4)
ax.plot(used[0, 0], used[0, 1], "o", color="#2a78d6", ms=7, zorder=5)
ax.annotate("0 m", used[0], textcoords="offset points", xytext=(6, 6), color="#2a78d6")
ax.plot(eyes[:, 0], eyes[:, 1], "^", color="#d64a2a", ms=5, label="cameras", zorder=5)
ax.set_aspect("equal")
ax.set_xlabel("east (m)")
ax.set_ylabel("north (m)")
ax.legend(loc="best", frameon=False)
ax.set_title("the guide and the photos, seen from above", loc="left")
fig.savefig(out / "plan.png", dpi=110)

order = np.argsort([-v.mean() for v in valid])[:6]
fig, ax = plt.subplots(len(order), 1, figsize=(16, len(order) * 16 * rows / cols + 2), constrained_layout=True)
for a, i in zip(ax, order):
    a.imshow(stack[i], extent=extent)
    a.set_title(f"{views[i]['name']} alone", loc="left")
fig.savefig(out / "single_views.png", dpi=80)
