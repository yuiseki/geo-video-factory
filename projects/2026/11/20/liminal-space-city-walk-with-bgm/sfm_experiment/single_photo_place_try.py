"""single_photo_place_try.py <photo> <plateau tris.npz> <out_dir> <east> <north> <hfov_deg> [--radius=80] [--grid=2]
                            [--eye=1.6] [--ground=<z>] [--pitch=0:30:2] [--roll=-2:2:2] [--fov-range=0.94:1.06:3]
                            [--key=<name in cams.json>] [--mesh-radius=600] [--sky=blue|bright|dark] [--dark-below=45]
                            [--heading=<from>:<to>]
Experiment: place ONE photograph on PLATEAU with nothing but the line between the buildings and the sky
(packages/pipeline/skyline_match.py). Photos of many photographers do not form an SfM model, so there is no pose to
start from: everything is searched. <east> <north> is a rough standing point in the frame of tris.npz (for example
the coordinates of the photo's page) and <hfov_deg> the horizontal field of view from the EXIF focal length.
Stage 1: the model's roofline at every point of a grid (radius, grid) at eye height above the ground.
Stage 2: for every pitch, roll and field of view, what the photo says about the roofline, against every place and
         every turn about the vertical. Stage 3: the same on a 0.5 m grid and in half-degree steps around the best.
--heading keeps the search to the headings from <from> clockwise to <to> (degrees from north), for a photo whose
compass direction is roughly known and whose roofline is too short to choose the turn alone.
Writes result.json (the pose and the next best places at least 10 m away: look at how far apart their costs are),
mask.jpg, costmap.png, overlay.jpg (PLATEAU's edges and roofline drawn on the photo at the found pose: the check
that matters), and cams.json + mesh.npz in the format of export_projection.py for blender_projection.py."""
import json
import sys
from itertools import product
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import skyline_match as sm  # noqa: E402

photo_path, tris_path, out = sys.argv[1:4]
X0, Y0, HFOV = map(float, sys.argv[4:7])
opts = dict(a[2:].split("=", 1) for a in sys.argv[7:] if a.startswith("--"))
RADIUS, GRID, EYE = float(opts.get("radius", 80)), float(opts.get("grid", 2)), float(opts.get("eye", 1.6))
BINS, TAU, WORK_W = 720, 5.0, 1300


def span(text):
    lo, hi, step = map(float, text.split(":"))
    return np.arange(lo, hi + step / 2, step)


PITCHES, ROLLS = span(opts.get("pitch", "0:30:2")), span(opts.get("roll", "-2:2:2"))
lo, hi, n = opts.get("fov-range", "0.94:1.06:3").split(":")
HEADINGS = [float(v) for v in opts["heading"].split(":")] if "heading" in opts else None
FOVS = HFOV * np.linspace(float(lo), float(hi), int(n))
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
Image.MAX_IMAGE_PIXELS = None

tris = np.load(tris_path)["tris"].astype(float)
ctr = tris.mean(1)
near = np.hypot(ctr[:, 0] - X0, ctr[:, 1] - Y0) < 250
ground = float(opts["ground"]) if "ground" in opts else float(np.percentile(tris[near][:, :, 2], 2))
EDGES = sm.unique_edges(tris)
full = Image.open(photo_path).convert("RGB")
W, H = full.size
small = full.resize((WORK_W, round(WORK_W * H / W)), Image.LANCZOS)
rgb = np.asarray(small)
w, h = small.size
print(f"photo {W} x {H}, worked at {w} x {h}; {len(EDGES[0])} edges; ground {ground:.2f}", flush=True)


def sky_mask(rgb, kind):
    """blue: blue, smooth, connected to the top or a side (clear day). bright: bright, smooth, connected to the top
    (overcast). dark: dark, smooth, connected to the top (night; unlit walls pass too, so look at mask.jpg)."""
    im = rgb.astype(np.float32)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    lum = im.mean(2)
    grad = np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1)) / 8
    if kind == "blue":
        cand = (b - r > 30) & (b > g) & (b > 80) & (grad < 6)
    elif kind == "dark":
        cand = (lum < float(opts.get("dark-below", 45))) & (grad < 3)
    else:
        cand = (lum > 170) & (grad < 5)
    cand = ndimage.binary_opening(cand, iterations=2)
    lab, _ = ndimage.label(cand)
    edge = np.concatenate([lab[0], lab[:, 0], lab[:, -1]]) if kind == "blue" else lab[0]
    ids = [i for i in np.unique(edge[edge > 0]) if (lab == i).sum() > 0.003 * lab.size]
    return ndimage.binary_closing(np.isin(lab, ids), iterations=2, border_value=0) | np.isin(lab, ids)


SKY = sky_mask(rgb, opts.get("sky", "blue"))
ov = rgb.copy()
ov[SKY] = (ov[SKY] * 0.4 + np.array([255, 0, 255]) * 0.6).astype(np.uint8)
Image.fromarray(ov).save(out / "mask.jpg", quality=85)
print(f"sky {SKY.mean():.0%} of the picture", flush=True)


def camera(heading, pitch, roll):
    """World (east, north, up) -> camera (x right, y down, z forward). roll > 0 turns the picture clockwise."""
    hd, p, r = np.radians([heading, pitch, roll])
    z = np.array([np.sin(hd) * np.cos(p), np.cos(hd) * np.cos(p), np.sin(p)])
    x = np.array([np.cos(hd), -np.sin(hd), 0.0])
    level = np.stack([x, np.cross(z, x), z])
    c, s = np.cos(r), np.sin(r)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]) @ level


def said(pitch, roll, fov):
    """What the photo says about the roofline when it looks north with this pitch, roll and field of view."""
    f = w / 2 / np.tan(np.radians(fov) / 2)
    az, el = sm.pixel_rays(w, h, f, w / 2, h / 2, 0.0, camera(0.0, pitch, roll), step=1)
    return sm.photo_skyline(az, el, SKY, bins=BINS)


def one_place(p):
    return sm.model_skyline(*EDGES, p, bins=BINS).astype(np.float32)


def one_pose(q):
    cost = sm.match_cost(said(*q), MODEL, tau=TAU)
    if HEADINGS:  # only the turns between the two headings, clockwise
        hd = np.arange(cost.shape[1]) * 360 / BINS
        cost = np.where((hd - HEADINGS[0]) % 360 <= (HEADINGS[1] - HEADINGS[0]) % 360, cost, np.inf)
    turn = np.nanargmin(cost, axis=1)
    return cost[np.arange(len(MODEL)), turn], turn


def search(places, poses, tag):
    global MODEL
    with Pool(8) as pool:
        MODEL = np.stack(pool.map(one_place, places, chunksize=32))
    with Pool(6) as pool:  # forked after MODEL is set
        res = pool.map(one_pose, poses)
    cost = np.array([r[0] for r in res])                      # (poses, places)
    turn = np.array([r[1] for r in res])
    ip, il = np.unravel_index(np.nanargmin(cost), cost.shape)
    best = dict(east=float(places[il, 0]), north=float(places[il, 1]), up=float(places[il, 2]),
                heading=float(turn[ip, il] * 360 / BINS), pitch=float(poses[ip][0]), roll=float(poses[ip][1]),
                hfov=float(poses[ip][2]), cost=float(cost[ip, il]))
    print(f"{tag}: {len(places)} places x {len(poses)} poses -> cost {best['cost']:.3f} at east {best['east']:.1f} "
          f"north {best['north']:.1f}, heading {best['heading']:.1f}, pitch {best['pitch']:.1f}, roll {best['roll']:.1f}, "
          f"hfov {best['hfov']:.1f}", flush=True)
    return best, cost, turn


xs = np.arange(X0 - RADIUS, X0 + RADIUS + GRID / 2, GRID)
gy, gx = np.meshgrid(np.arange(Y0 - RADIUS, Y0 + RADIUS + GRID / 2, GRID), xs, indexing="ij")
places = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, ground + EYE)], 1)
poses = list(product(PITCHES, ROLLS, FOVS))
coarse, cost, turn = search(places, poses, "coarse")
per_place = np.nanmin(cost, axis=0)

# the next best places at least 10 m from the better ones: how alone is the answer?
others, order = [], np.argsort(per_place)
for i in order:
    if all(np.hypot(*(places[i, :2] - places[j, :2])) >= 10 for j in others):
        others.append(int(i))
    if len(others) == 6:
        break
rivals = []
for i in others:
    ip = int(np.nanargmin(cost[:, i]))
    rivals.append(dict(east=float(places[i, 0]), north=float(places[i, 1]), cost=float(per_place[i]),
                       heading=float(turn[ip, i] * 360 / BINS), pitch=float(poses[ip][0]), hfov=float(poses[ip][2])))
    print(f"  place {places[i, 0]:7.1f} {places[i, 1]:7.1f}  cost {per_place[i]:.3f}  heading {rivals[-1]['heading']:.1f}  "
          f"pitch {rivals[-1]['pitch']:.0f}  hfov {rivals[-1]['hfov']:.1f}", flush=True)

fig, ax = plt.subplots(figsize=(9, 8), dpi=100)
m = per_place.reshape(gx.shape)
im = ax.imshow(m, origin="lower", extent=(xs[0] - GRID / 2, xs[-1] + GRID / 2, gy[0, 0] - GRID / 2, gy[-1, 0] + GRID / 2),
               cmap="viridis_r", vmin=np.nanmin(m), vmax=np.nanpercentile(m, 50))
fp = tris[near & (np.abs(tris[:, :, 2].min(1) - ground) < 3)]
for t in fp[::7]:
    ax.plot(t[[0, 1, 2, 0], 0], t[[0, 1, 2, 0], 1], color="#fff", lw=0.2, alpha=0.5)
ax.plot(X0, Y0, "o", mfc="none", mec="red", ms=10, mew=1.5, label="given")
ax.plot(coarse["east"], coarse["north"], "x", color="white", ms=10, mew=2, label="found")
ax.set_xlim(xs[0], xs[-1]); ax.set_ylim(gy[0, 0], gy[-1, 0]); ax.legend()
ax.set_title("skyline cost of the best pose at every standing point (yellow = low)")
fig.colorbar(im); fig.tight_layout(); fig.savefig(out / "costmap.png"); plt.close(fig)

fx = np.arange(coarse["east"] - 4, coarse["east"] + 4.01, 0.5)
fy, fxg = np.meshgrid(np.arange(coarse["north"] - 4, coarse["north"] + 4.01, 0.5), fx, indexing="ij")
fine_places = np.stack([fxg.ravel(), fy.ravel(), np.full(fxg.size, ground + EYE)], 1)
fine_poses = list(product(np.arange(coarse["pitch"] - 2, coarse["pitch"] + 2.01, 0.5),
                          np.arange(coarse["roll"] - 2, coarse["roll"] + 2.01, 0.5),
                          coarse["hfov"] * np.linspace(0.96, 1.04, 5)))
best, _, _ = search(fine_places, fine_poses, "fine")

# ---- the check: PLATEAU drawn on the photo at the found pose
R = camera(best["heading"], best["pitch"], best["roll"])
eye = np.array([best["east"], best["north"], best["up"]])
f = W / 2 / np.tan(np.radians(best["hfov"]) / 2)
a, b = EDGES
keep = (np.hypot(*(0.5 * (a + b) - eye)[:, :2].T) < 900)
pa, pb = (a[keep] - eye) @ R.T, (b[keep] - eye) @ R.T
front = (pa[:, 2] > 1) & (pb[:, 2] > 1)
ua, ub = pa[front, :2] / pa[front, 2:3] * f + [W / 2, H / 2], pb[front, :2] / pb[front, 2:3] * f + [W / 2, H / 2]
seen = ((np.minimum(ua[:, 0], ub[:, 0]) < W) & (np.maximum(ua[:, 0], ub[:, 0]) > 0)
        & (np.minimum(ua[:, 1], ub[:, 1]) < H) & (np.maximum(ua[:, 1], ub[:, 1]) > 0))
sc = 1600 / W
canvas = full.resize((1600, round(H * sc)), Image.LANCZOS)
draw = ImageDraw.Draw(canvas)
for p, q in zip(ua[seen] * sc, ub[seen] * sc):
    draw.line([tuple(p), tuple(q)], fill=(255, 230, 0), width=1)
sky_model = sm.model_skyline(*EDGES, eye, bins=BINS)
azc = np.radians((np.arange(BINS) + 0.5) * 360 / BINS)
el = np.radians(np.nan_to_num(sky_model, nan=0.0))
d = np.stack([np.sin(azc) * np.cos(el), np.cos(azc) * np.cos(el), np.sin(el)], 1) @ R.T
ok = d[:, 2] > 0.1
for u in d[ok, :2] / d[ok, 2:3] * f * sc + [800, H * sc / 2]:
    draw.ellipse([u[0] - 4, u[1] - 4, u[0] + 4, u[1] + 4], fill=(255, 0, 0))
canvas.save(out / "overlay.jpg", quality=88)

key = opts.get("key", Path(photo_path).stem[:3])
fov_v = float(np.degrees(2 * np.arctan(H / 2 / f)))
cams = {key: dict(name=Path(photo_path).name, photo=str(Path(photo_path).resolve()), eye=eye.tolist(), Rw=R.tolist(),
                  fov_v=fov_v, width=W, height=H, model="PINHOLE", params=[f, f, W / 2, H / 2], fit_roll_deg=best["roll"])}
json.dump(cams, open(out / "cams.json", "w"), indent=1)
keep = np.hypot(ctr[:, 0] - eye[0], ctr[:, 1] - eye[1]) < float(opts.get("mesh-radius", 600))
np.savez_compressed(out / "mesh.npz", tris=tris[keep].astype(np.float32), ground=ground)
json.dump(dict(photo=Path(photo_path).name, given=[X0, Y0, HFOV], ground=ground, eye_height=EYE, best=best, coarse=coarse,
               rivals=rivals, moved_m=float(np.hypot(best["east"] - X0, best["north"] - Y0))), open(out / "result.json", "w"), indent=1)
print(f"placed {np.hypot(best['east'] - X0, best['north'] - Y0):.1f} m from the given point; fov_v {fov_v:.1f}; "
      f"saved result.json, mask.jpg, costmap.png, overlay.jpg, cams.json, mesh.npz ({int(keep.sum())} triangles)")
