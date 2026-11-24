"""One photograph placed on a city model, with nothing but the line between the buildings and the sky.

Photographs of many photographers do not form an SfM model, so there is no pose to start from: everything is
searched (skyline_match.py). Given a rough standing point and the horizontal field of view from the EXIF focal length,
  1. the model's roofline at every point of a grid at eye height above the ground,
  2. for every pitch, roll and field of view, what the photo says about the roofline, against every place and every
     turn about the vertical,
  3. the same on a 0.5 m grid and in half-degree steps around the best.

    python3 photo_place.py <photo> <tris.npz> <out_dir> <east> <north> <hfov_deg> [--radius=80] [--grid=2] [--eye=1.6]
        [--ground=<z>] [--pitch=0:30:2] [--roll=-2:2:2] [--fov-range=0.94:1.06:3] [--key=<name in cams.json>]
        [--mesh-radius=600] [--sky=blue|bright|dark] [--dark-below=45] [--heading=<from>:<to>]

<tris.npz> holds "tris" (n, 3, 3) in east, north, up metres (plateau_mesh.py); <east> <north> are in its frame.
--heading keeps the search to the headings from <from> clockwise to <to> (degrees from north), for a photo whose
compass direction is roughly known and whose roofline is too short to choose the turn alone.
Writes result.json (the pose and the next best places at least 10 m away: look at how far apart their costs are),
mask.jpg (the sky that was read), costmap.png (the cost of the best pose at every standing point, yellow = low),
overlay.jpg (the model's edges and roofline drawn on the photo at the found pose: the check that matters), and
cams.json + mesh.npz for a projection of the photo onto the model. Nothing is printed during the coarse search.
"""
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parents[1]) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
import json
import multiprocessing
import sys
from itertools import product
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from geo import skyline_match as sm

BINS, TAU, WORK_W = 720, 5.0, 1300
SKIES = ("blue", "bright", "dark")
_STATE = {}  # what the worker processes read; they are forked after it is filled


def span(text):
    """'lo:hi:step' as the values from lo to hi, hi included."""
    lo, hi, step = map(float, text.split(":"))
    return np.arange(lo, hi + step / 2, step)


def sky_mask(rgb, kind="blue", dark_below=45.0):
    """The sky of a picture (h, w, 3) as a boolean mask.
    blue: blue, smooth, connected to the top or a side (clear day). bright: bright, smooth, connected to the top
    (overcast). dark: dark, smooth, connected to the top (night; unlit walls pass too, so look at mask.jpg)."""
    if kind not in SKIES:
        raise ValueError(f"sky must be one of {', '.join(SKIES)}: {kind}")
    im = np.asarray(rgb).astype(np.float32)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    lum = im.mean(2)
    grad = np.hypot(ndimage.sobel(lum, 0), ndimage.sobel(lum, 1)) / 8
    if kind == "blue":
        cand = (b - r > 30) & (b > g) & (b > 80) & (grad < 6)
    elif kind == "dark":
        cand = (lum < dark_below) & (grad < 3)
    else:
        cand = (lum > 170) & (grad < 5)
    cand = ndimage.binary_opening(cand, iterations=2)
    lab, _ = ndimage.label(cand)
    edge = np.concatenate([lab[0], lab[:, 0], lab[:, -1]]) if kind == "blue" else lab[0]
    ids = [i for i in np.unique(edge[edge > 0]) if (lab == i).sum() > 0.003 * lab.size]
    kept = np.isin(lab, ids)
    return ndimage.binary_closing(kept, iterations=2, border_value=0) | kept


def camera(heading, pitch, roll):
    """World (east, north, up) -> camera (x right, y down, z forward). roll > 0 turns the picture clockwise."""
    hd, p, r = np.radians([heading, pitch, roll])
    z = np.array([np.sin(hd) * np.cos(p), np.cos(hd) * np.cos(p), np.sin(p)])
    x = np.array([np.cos(hd), -np.sin(hd), 0.0])
    level = np.stack([x, np.cross(z, x), z])
    c, s = np.cos(r), np.sin(r)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]) @ level


def said(sky, pitch, roll, fov, bins=BINS):
    """What the picture whose sky mask this is says about the roofline when it looks north with this pitch, roll and
    horizontal field of view."""
    h, w = sky.shape
    f = w / 2 / np.tan(np.radians(fov) / 2)
    az, el = sm.pixel_rays(w, h, f, w / 2, h / 2, 0.0, camera(0.0, pitch, roll), step=1)
    return sm.photo_skyline(az, el, sky, bins=bins)


def _one_place(p):
    return sm.model_skyline(*_STATE["edges"], p, bins=_STATE["bins"]).astype(np.float32)


def _one_pose(q):
    bins, headings, model = _STATE["bins"], _STATE["headings"], _STATE["model"]
    cost = sm.match_cost(said(_STATE["sky"], *q, bins=bins), model, tau=_STATE["tau"])
    if headings:  # only the turns between the two headings, clockwise
        hd = np.arange(cost.shape[1]) * 360 / bins
        cost = np.where((hd - headings[0]) % 360 <= (headings[1] - headings[0]) % 360, cost, np.inf)
    turn = np.nanargmin(cost, axis=1)
    return cost[np.arange(len(model)), turn], turn


def _map(func, items, workers, chunksize):
    if not workers or workers == 1:
        return [func(i) for i in items]
    with multiprocessing.get_context("fork").Pool(workers) as pool:
        return pool.map(func, items, chunksize=chunksize)


def search(edges, sky, places, poses, headings=None, bins=BINS, tau=TAU, workers=(8, 6)):
    """Every place (n, 3) against every pose (pitch, roll, hfov) and every turn about the vertical.
    Returns the best as a dict, and two arrays (poses, places): the cost of the best turn, and that turn in bins.
    workers is the number of processes for the model's rooflines and for the poses; None works in this process."""
    at_places, at_poses = workers or (1, 1)
    _STATE.update(edges=edges, sky=np.asarray(sky, bool), bins=bins, tau=tau, headings=headings, model=None)
    try:
        _STATE["model"] = np.stack(_map(_one_place, places, at_places, 32))
        res = _map(_one_pose, poses, at_poses, None)  # forked after the model is set
    finally:
        _STATE.clear()
    cost = np.array([r[0] for r in res])
    turn = np.array([r[1] for r in res])
    ip, il = np.unravel_index(np.nanargmin(cost), cost.shape)
    best = dict(east=float(places[il, 0]), north=float(places[il, 1]), up=float(places[il, 2]),
                heading=float(turn[ip, il] * 360 / bins), pitch=float(poses[ip][0]), roll=float(poses[ip][1]),
                hfov=float(poses[ip][2]), cost=float(cost[ip, il]))
    return best, cost, turn


def describe(tag, best, places, poses):
    return (f"{tag}: {len(places)} places x {len(poses)} poses -> cost {best['cost']:.3f} at east {best['east']:.1f} "
            f"north {best['north']:.1f}, heading {best['heading']:.1f}, pitch {best['pitch']:.1f}, "
            f"roll {best['roll']:.1f}, hfov {best['hfov']:.1f}")


def grid_places(x0, y0, radius, step, z):
    """Standing points on a square grid around (x0, y0), all at the height z: (n, 3), east running fastest, and the
    grid's east and north values."""
    xs = np.arange(x0 - radius, x0 + radius + step / 2, step)
    ys = np.arange(y0 - radius, y0 + radius + step / 2, step)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    return np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, float(z))], 1), xs, ys


def ground_level(tris, x0, y0, radius=250.0):
    """The height of the ground near a point: the low end (2nd percentile) of the model within the radius."""
    ctr = tris.mean(1)
    near = np.hypot(ctr[:, 0] - x0, ctr[:, 1] - y0) < radius
    if not near.any():
        raise ValueError(f"no triangles within {radius:g} m of east {x0:g} north {y0:g}")
    return float(np.percentile(tris[near][:, :, 2], 2))


def rivals(places, poses, cost, turn, bins=BINS, count=6, apart=10.0):
    """The best places that are at least `apart` metres from the better ones, best first: how alone is the answer?"""
    per_place = np.nanmin(cost, axis=0)
    chosen = []
    for i in np.argsort(per_place):
        if all(np.hypot(*(places[i, :2] - places[j, :2])) >= apart for j in chosen):
            chosen.append(int(i))
        if len(chosen) == count:
            break
    out = []
    for i in chosen:
        ip = int(np.nanargmin(cost[:, i]))
        out.append(dict(east=float(places[i, 0]), north=float(places[i, 1]), cost=float(per_place[i]),
                        heading=float(turn[ip, i] * 360 / bins), pitch=float(poses[ip][0]), hfov=float(poses[ip][2])))
    return out


def fine_space(coarse, half=4.0, step=0.5, angle=2.0, roll=2.0, fov=5):
    """The places and poses of the second search: half a metre and half a degree around the coarse answer, and `fov`
    fields of view within 4 % of it."""
    places, _, _ = grid_places(coarse["east"], coarse["north"], half, step, coarse["up"])
    scales = np.linspace(0.96, 1.04, fov) if fov > 1 else np.array([1.0])
    poses = list(product(np.arange(coarse["pitch"] - angle, coarse["pitch"] + angle + 0.01, 0.5),
                         np.arange(coarse["roll"] - roll, coarse["roll"] + roll + 0.01, 0.5),
                         coarse["hfov"] * scales))
    return places, poses


RAMP = np.array([[253, 231, 37], [33, 145, 140], [68, 1, 84]], float)  # low cost to high


def costmap(per_place, xs, ys, tris, ground, given, found, size=800):
    """The cost of the best pose at every standing point as a picture, north up: yellow is low, purple is the median
    or worse. White lines are the model near the ground, the red ring the given point, the white cross the found."""
    m = np.asarray(per_place, float).reshape(len(ys), len(xs))
    lo, hi = np.nanmin(m), np.nanpercentile(m, 50)
    t = np.clip((np.nan_to_num(m, nan=hi) - lo) / max(hi - lo, 1e-9), 0, 1) * 2
    i = np.minimum(t.astype(int), 1)
    rgb = RAMP[i] + (RAMP[i + 1] - RAMP[i]) * (t - i)[..., None]
    k = max(1, size // max(m.shape))
    im = Image.fromarray(rgb[::-1].astype(np.uint8)).resize((len(xs) * k, len(ys) * k), Image.NEAREST)
    step = xs[1] - xs[0] if len(xs) > 1 else 1.0

    def px(e, n):
        return (e - xs[0] + step / 2) / step * k, (ys[-1] + step / 2 - n) / step * k

    draw = ImageDraw.Draw(im)
    ctr = tris.mean(1)
    inside = ((np.abs(ctr[:, 0] - xs.mean()) < np.ptp(xs) / 2 + 30) & (np.abs(ctr[:, 1] - ys.mean()) < np.ptp(ys) / 2 + 30)
              & (np.abs(tris[:, :, 2].min(1) - ground) < 3))
    for tri in tris[inside][::7]:
        draw.line([px(*p[:2]) for p in tri[[0, 1, 2, 0]]], fill=(255, 255, 255), width=1)
    gx, gy = px(*given)
    draw.ellipse([gx - 7, gy - 7, gx + 7, gy + 7], outline=(255, 0, 0), width=2)
    fx, fy = px(*found)
    draw.line([fx - 7, fy - 7, fx + 7, fy + 7], fill=(255, 255, 255), width=3)
    draw.line([fx - 7, fy + 7, fx + 7, fy - 7], fill=(255, 255, 255), width=3)
    return im


def overlay(full, edges, best, bins=BINS, width=1600):
    """The model drawn on the photo at the pose: its edges within 900 m in yellow, its roofline as red dots."""
    W, H = full.size
    R = camera(best["heading"], best["pitch"], best["roll"])
    eye = np.array([best["east"], best["north"], best["up"]])
    f = W / 2 / np.tan(np.radians(best["hfov"]) / 2)
    a, b = edges
    keep = np.hypot(*(0.5 * (a + b) - eye)[:, :2].T) < 900
    pa, pb = (a[keep] - eye) @ R.T, (b[keep] - eye) @ R.T
    front = (pa[:, 2] > 1) & (pb[:, 2] > 1)
    ua = pa[front, :2] / pa[front, 2:3] * f + [W / 2, H / 2]
    ub = pb[front, :2] / pb[front, 2:3] * f + [W / 2, H / 2]
    seen = ((np.minimum(ua[:, 0], ub[:, 0]) < W) & (np.maximum(ua[:, 0], ub[:, 0]) > 0)
            & (np.minimum(ua[:, 1], ub[:, 1]) < H) & (np.maximum(ua[:, 1], ub[:, 1]) > 0))
    sc = width / W
    canvas = full.resize((width, round(H * sc)), Image.LANCZOS)
    draw = ImageDraw.Draw(canvas)
    for p, q in zip(ua[seen] * sc, ub[seen] * sc):
        draw.line([tuple(p), tuple(q)], fill=(255, 230, 0), width=1)
    azc = np.radians((np.arange(bins) + 0.5) * 360 / bins)
    el = np.radians(np.nan_to_num(sm.model_skyline(a, b, eye, bins=bins), nan=0.0))
    d = np.stack([np.sin(azc) * np.cos(el), np.cos(azc) * np.cos(el), np.sin(el)], 1) @ R.T
    ok = d[:, 2] > 0.1
    for u in d[ok, :2] / d[ok, 2:3] * f * sc + [width / 2, H * sc / 2]:
        draw.ellipse([u[0] - 4, u[1] - 4, u[0] + 4, u[1] + 4], fill=(255, 0, 0))
    return canvas


def cam_entry(photo_path, size, best):
    """The found pose in the format the projection reads (one value of cams.json)."""
    W, H = size
    f = W / 2 / np.tan(np.radians(best["hfov"]) / 2)
    return dict(name=Path(photo_path).name, photo=str(Path(photo_path).resolve()),
                eye=[best["east"], best["north"], best["up"]],
                Rw=camera(best["heading"], best["pitch"], best["roll"]).tolist(),
                fov_v=float(np.degrees(2 * np.arctan(H / 2 / f))), width=W, height=H, model="PINHOLE",
                params=[f, f, W / 2, H / 2], fit_roll_deg=best["roll"])


def place(photo_path, tris_path, out, x0, y0, hfov, radius=80.0, grid=2.0, eye=1.6, ground=None, pitch="0:30:2",
          roll="-2:2:2", fov_range="0.94:1.06:3", key=None, mesh_radius=600.0, sky="blue", dark_below=45.0,
          heading=None, work_w=WORK_W, bins=BINS, workers=(8, 6), fine_half=4.0, fine_roll=2.0, fine_fov=5, log=print):
    """Search the pose of one photo and write the files named at the top into `out`. Returns what result.json holds."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with np.load(tris_path) as data:
        tris = data["tris"].astype(float)
    ground = ground_level(tris, x0, y0) if ground is None else float(ground)
    edges = sm.unique_edges(tris)
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(photo_path) as opened:
        full = opened.convert("RGB")
    W, H = full.size
    rgb = np.asarray(full.resize((work_w, round(work_w * H / W)), Image.LANCZOS))
    log(f"photo {W} x {H}, worked at {rgb.shape[1]} x {rgb.shape[0]}; {len(edges[0])} edges; ground {ground:.2f}")
    mask = sky_mask(rgb, sky, dark_below)
    shown = rgb.copy()
    shown[mask] = (shown[mask] * 0.4 + np.array([255, 0, 255]) * 0.6).astype(np.uint8)
    Image.fromarray(shown).save(out / "mask.jpg", quality=85)
    log(f"sky {mask.mean():.0%} of the picture")

    lo, hi, n = fov_range.split(":")
    places, xs, ys = grid_places(x0, y0, radius, grid, ground + eye)
    poses = list(product(span(pitch), span(roll), hfov * np.linspace(float(lo), float(hi), int(n))))
    coarse, cost, turn = search(edges, mask, places, poses, heading, bins, workers=workers)
    log(describe("coarse", coarse, places, poses))
    others = rivals(places, poses, cost, turn, bins)
    for r in others:
        log(f"  place {r['east']:7.1f} {r['north']:7.1f}  cost {r['cost']:.3f}  heading {r['heading']:.1f}  "
            f"pitch {r['pitch']:.0f}  hfov {r['hfov']:.1f}")
    costmap(np.nanmin(cost, axis=0), xs, ys, tris, ground, (x0, y0), (coarse["east"], coarse["north"])).save(
        out / "costmap.png")

    fine_places, fine_poses = fine_space(coarse, half=fine_half, roll=fine_roll, fov=fine_fov)
    best, _, _ = search(edges, mask, fine_places, fine_poses, heading, bins, workers=workers)
    log(describe("fine", best, fine_places, fine_poses))

    overlay(full, edges, best, bins).save(out / "overlay.jpg", quality=88)
    cam = cam_entry(photo_path, (W, H), best)
    (out / "cams.json").write_text(json.dumps({key or Path(photo_path).stem[:3]: cam}, indent=1))
    ctr = tris.mean(1)
    keep = np.hypot(ctr[:, 0] - best["east"], ctr[:, 1] - best["north"]) < mesh_radius
    np.savez_compressed(out / "mesh.npz", tris=tris[keep].astype(np.float32), ground=ground)
    moved = float(np.hypot(best["east"] - x0, best["north"] - y0))
    result = dict(photo=Path(photo_path).name, given=[x0, y0, hfov], ground=ground, eye_height=eye, best=best,
                  coarse=coarse, rivals=others, moved_m=moved)
    (out / "result.json").write_text(json.dumps(result, indent=1))
    log(f"placed {moved:.1f} m from the given point; fov_v {cam['fov_v']:.1f}; saved result.json, mask.jpg, "
        f"costmap.png, overlay.jpg, cams.json, mesh.npz ({int(keep.sum())} triangles)")
    return result


NUMBERS = ("radius", "grid", "eye", "ground", "mesh_radius", "dark_below")
TEXTS = ("pitch", "roll", "fov_range", "key", "sky")


def parse_args(argv):
    """[photo, tris, out, east, north, hfov, options] from the command line; exits on anything it does not know."""
    paths = [a for a in argv if not a.startswith("--")]
    if len(paths) != 6:
        raise SystemExit(__doc__)
    opts = {}
    for arg in argv:
        if not arg.startswith("--"):
            continue
        name, _, value = arg[2:].partition("=")
        name = name.replace("-", "_")
        if name in NUMBERS:
            opts[name] = float(value)
        elif name in TEXTS:
            opts[name] = value
        elif name == "heading":
            lo, hi = value.split(":")
            opts[name] = (float(lo), float(hi))
        else:
            raise SystemExit(f"unknown option {arg}\n\n{__doc__}")
    return paths[:3] + [float(v) for v in paths[3:]] + [opts]


def main(argv=None):
    *args, opts = parse_args(sys.argv[1:] if argv is None else argv)
    place(*args, **opts, log=lambda s: print(s, flush=True))


if __name__ == "__main__":
    main()
