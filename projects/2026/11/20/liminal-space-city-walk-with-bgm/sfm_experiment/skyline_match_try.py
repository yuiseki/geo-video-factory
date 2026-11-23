"""skyline_match_try.py <sparse_model_dir> <images_dir> <placement.json> <plateau tris.npz> <out_dir>
                        [grid_m=2] [margin_m=30] [heights above the ground, comma separated = 1.5,3,4.5,6,7.5]
Experiment: can one photograph be placed on PLATEAU by exhaustive search, with the line between the buildings
and the sky as the only cost (packages/pipeline/skyline_match.py)? The photos here have known poses (an SfM
model placed on PLATEAU), so the answer can be checked. Roll and pitch are taken from the known pose; the
search covers the standing point (a grid around the cameras, a few heights) and every turn about the vertical.
Stage 1 (always): the sky masks, the photo's roofline against the model's at the true pose (masks.jpg,
profiles.png), and what each photo says about the roofline, for skyline_refit_try.py (photos.npz). Stage 2: the search (model_grid.npz is kept and reused), result.json and costmaps.png."""
import zlib  # noqa: F401
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pycolmap
from PIL import Image
from scipy import ndimage
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import skyline_match as sm  # noqa: E402

model, images, placement, tris_path, out = sys.argv[1:6]
GRID = float(sys.argv[6]) if len(sys.argv) > 6 else 2.0
MARGIN = float(sys.argv[7]) if len(sys.argv) > 7 else 30.0
HEIGHTS = [float(h) for h in (sys.argv[8] if len(sys.argv) > 8 else "1.5,3,4.5,6,7.5").split(",")]
BINS, STEP, TAU = 720, 4, 5.0
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
Image.MAX_IMAGE_PIXELS = None

pl = json.load(open(placement))
B, s, t, ground = np.array(pl["basis"]), pl["scale"], np.array(pl["t"]), pl["ground"]
c, sn = np.cos(pl["yaw"]), np.sin(pl["yaw"])
A = np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1]])
o = np.array([*pl["centroid"], pl["z_cam_median"]])
rec = pycolmap.Reconstruction(model)
views = []
for im in sorted(rec.images.values(), key=lambda im: im.name):
    cam = rec.cameras[im.camera_id]
    assert "SIMPLE_RADIAL" in str(cam.model), cam.model
    T = im.cam_from_world()
    Rc, tc = T.rotation.matrix(), np.array(T.translation)
    R = Rc @ B.T @ A.T                                   # world (east, north, up) -> camera
    tw = -R @ t + s * (Rc @ B.T @ o + tc)
    views.append(dict(name=im.name, R=R, eye=-R.T @ tw, cam=(cam.width, cam.height, *map(float, cam.params))))
eyes = np.array([v["eye"] for v in views])
EDGES = sm.unique_edges(np.load(tris_path)["tris"])
print(f"{len(views)} photos, {len(EDGES[0])} edges; cameras {np.median(eyes[:, 2]) - ground:.2f} m above the ground", flush=True)


def sky_mask(rgb):
    """Blue, smooth, and connected to the top or a side of the picture (daytime, clear sky)."""
    im = rgb.astype(np.float32)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    lum = im.mean(2)
    grad = np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1)) / 8
    cand = (b - r > 30) & (b > g) & (b > 80) & (grad < 6)
    cand = ndimage.binary_opening(cand, iterations=2)
    lab, _ = ndimage.label(cand)
    edge = np.concatenate([lab[0], lab[:, 0], lab[:, -1]])
    ids = [i for i in np.unique(edge[edge > 0]) if (lab == i).sum() > 0.003 * lab.size]
    return ndimage.binary_closing(np.isin(lab, ids), iterations=2, border_value=0) | np.isin(lab, ids)


def heading_of(R):
    """Azimuth of the optical axis."""
    return float(np.degrees(np.arctan2(R[2, 0], R[2, 1])) % 360)


# ---- stage 1: what each photo says about the roofline, against the model at the true pose
thumbs = []
for v in views:
    photo = Image.open(Path(images) / v["name"]).convert("RGB").reduce(STEP)
    rgb = np.asarray(photo)
    w, h, f, cx, cy, k = v["cam"]
    az, el = sm.pixel_rays(int(w), int(h), f, cx, cy, k, v["R"], step=STEP)
    assert az.shape == rgb.shape[:2], (az.shape, rgb.shape)
    sky = sky_mask(rgb)
    v["photo"] = sm.photo_skyline(az, el, sky, bins=BINS)
    v["truth"] = sm.model_skyline(*EDGES, v["eye"], bins=BINS)
    c0 = sm.match_cost(v["photo"], v["truth"][None], tau=TAU)[0]
    v["cost_true"], v["turn_at_true_place"] = float(c0[0]), float(((np.argmin(c0) + BINS // 2) % BINS - BINS // 2) * 360 / BINS)
    n = {key: int((~np.isnan(a)).sum()) for key, a in v["photo"].items()}
    print(f"{v['name'][-7:-4]}  heading {heading_of(v['R']):5.1f}  bins sky {n['sky']:3d} floor {n['floor']:3d} ceil {n['ceil']:3d}  "
          f"cost at the true pose {v['cost_true']:.2f}  best turn at the true place {v['turn_at_true_place']:+6.1f} deg "
          f"(cost {np.min(c0):.2f})", flush=True)
    ov = rgb[::2, ::2].copy()
    m = sky[::2, ::2]
    ov[m] = (ov[m] * 0.4 + np.array([255, 0, 255]) * 0.6).astype(np.uint8)
    thumbs.append(ov)
th, tw_ = thumbs[0].shape[:2]
sheet = np.zeros((5 * th, 8 * tw_, 3), np.uint8)
for i, ov in enumerate(thumbs):
    sheet[(i // 8) * th:(i // 8 + 1) * th, (i % 8) * tw_:(i % 8 + 1) * tw_] = ov
Image.fromarray(sheet).save(out / "masks.jpg", quality=85)

centres = (np.arange(BINS) + 0.5) * 360 / BINS
fig, axes = plt.subplots(5, 8, figsize=(32, 16), dpi=70)
for v, ax in zip(views, axes.ravel()):
    rel = (centres - heading_of(v["R"]) + 180) % 360 - 180
    order = np.argsort(rel)
    keep = np.abs(rel[order]) < 60
    ax.plot(rel[order][keep], np.nan_to_num(v["truth"], nan=0.0)[order][keep], color="#444", lw=1, label="PLATEAU at the true pose")
    ax.plot(rel, v["photo"]["sky"], ".", color="#1f77b4", ms=3, label="photo: roofline")
    ax.plot(rel, v["photo"]["floor"], "^", color="#d62728", ms=3, label="photo: at least")
    ax.plot(rel, v["photo"]["ceil"], "v", color="#2ca02c", ms=3, label="photo: at most")
    ax.set_xlim(-60, 60); ax.set_ylim(-10, 90); ax.grid(alpha=.3)
    ax.set_title(f"{v['name'][-7:-4]}  cost {v['cost_true']:.2f}", fontsize=9)
axes[0, 0].legend(fontsize=6)
fig.supxlabel("azimuth from the optical axis (deg)"); fig.supylabel("elevation (deg)")
fig.tight_layout(); fig.savefig(out / "profiles.png"); plt.close(fig)
np.savez_compressed(out / "photos.npz", names=[v["name"] for v in views], eyes=eyes, R=[v["R"] for v in views],
                    cam=[v["cam"] for v in views], ground=ground, bins=BINS,
                    **{key: np.array([v["photo"][key] for v in views], np.float32) for key in ("sky", "floor", "ceil")})
print("saved masks.jpg, profiles.png, photos.npz", flush=True)
if GRID <= 0:
    sys.exit(0)

# ---- stage 2: every standing point of a grid, every height, every turn
xs = np.arange(eyes[:, 0].min() - MARGIN, eyes[:, 0].max() + MARGIN + GRID / 2, GRID)
ys = np.arange(eyes[:, 1].min() - MARGIN, eyes[:, 1].max() + MARGIN + GRID / 2, GRID)
zs = ground + np.array(HEIGHTS)
gz, gy, gx = np.meshgrid(zs, ys, xs, indexing="ij")
places = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], 1)


def one(p):
    return sm.model_skyline(*EDGES, p, bins=BINS).astype(np.float32)


cache = out / "model_grid.npz"
if cache.exists() and np.load(cache)["places"].shape == places.shape and np.allclose(np.load(cache)["places"], places):
    grid = np.load(cache)["skyline"]
else:
    with Pool(4) as pool:
        grid = np.stack(pool.map(one, places, chunksize=64))
    np.savez_compressed(cache, places=places, skyline=grid)
print(f"grid {len(xs)} x {len(ys)} x {len(zs)} = {len(places)} places at {GRID} m; "
      f"{np.isnan(grid).mean():.0%} of the directions are open", flush=True)

rows, maps = [], []
for v in views:
    cost = sm.match_cost(v["photo"], grid, tau=TAU)            # (places, turns)
    best_turn = np.argmin(cost, axis=1)
    per_place = cost[np.arange(len(places)), best_turn]
    win = int(np.argmin(per_place))
    turn = ((best_turn[win] + BINS // 2) % BINS - BINS // 2) * 360 / BINS
    near = int(np.argmin(np.linalg.norm(places - v["eye"], axis=1)))  # the grid place nearest to the truth
    row = dict(name=v["name"], true_eye=v["eye"].tolist(), found=places[win].tolist(),
               error_m=float(np.hypot(*(places[win, :2] - v["eye"][:2]))), error_z_m=float(places[win, 2] - v["eye"][2]),
               error_turn_deg=float(turn), cost_found=float(per_place[win]), cost_true_pose=v["cost_true"],
               cost_near_truth=float(cost[near, 0]), rank_of_truth=int((per_place < cost[near, 0]).sum()) + 1,
               bins={key: int((~np.isnan(a)).sum()) for key, a in v["photo"].items()})
    rows.append(row)
    maps.append(per_place.reshape(len(zs), len(ys), len(xs)).min(0))
    print(f"{v['name'][-7:-4]}  found {row['error_m']:6.1f} m away, {row['error_z_m']:+5.1f} m in height, turned {turn:+7.1f} deg  "
          f"cost {row['cost_found']:.2f} (near the truth {row['cost_near_truth']:.2f}, rank {row['rank_of_truth']} of {len(places)})",
          flush=True)

err = np.array([r["error_m"] for r in rows])
turn = np.abs([r["error_turn_deg"] for r in rows])
summary = dict(photos=len(rows), grid_m=GRID, margin_m=MARGIN, heights=HEIGHTS, places=len(places), bins=BINS, tau=TAU,
               median_error_m=float(np.median(err)), within_5m=int((err <= 5).sum()), within_10m=int((err <= 10).sum()),
               turn_within_3deg=int((turn <= 3).sum()), both=int(((err <= 5) & (turn <= 3)).sum()))
print(summary, flush=True)
json.dump(dict(summary=summary, photos=rows), open(out / "result.json", "w"), indent=1)

fig, axes = plt.subplots(5, 8, figsize=(32, 20), dpi=70)
for v, r, m, ax in zip(views, rows, maps, axes.ravel()):
    ax.imshow(m, origin="lower", extent=(xs[0] - GRID / 2, xs[-1] + GRID / 2, ys[0] - GRID / 2, ys[-1] + GRID / 2),
              cmap="viridis_r", vmin=np.nanmin(m), vmax=np.nanpercentile(m, 60))
    ax.plot(*v["eye"][:2], "o", mfc="none", mec="red", ms=10, mew=1.5)
    ax.plot(*r["found"][:2], "x", color="white", ms=8, mew=1.5)
    ax.set_title(f"{v['name'][-7:-4]}  {r['error_m']:.0f} m, {r['error_turn_deg']:+.0f} deg", fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])
fig.suptitle("cost of the best turn and height at every standing point (dark = low). red circle: truth, white cross: found")
fig.tight_layout(); fig.savefig(out / "costmaps.png"); plt.close(fig)
print("saved result.json, costmaps.png", flush=True)
