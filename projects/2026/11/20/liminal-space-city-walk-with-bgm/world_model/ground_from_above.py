"""ground_from_above.py <work_dir> <scene tris.npz> <ground_ortho out dir> <out_dir> [--centre=x,y] [--half=160]
       [--res=0.1] [--z=<ground height>] [--above=40] [--keep=8] [--few=3] [--zoom=18] [--dim=1.0] [--near=20] [--align=2] [--reach=6] [--model=similarity|homography]
       <cams.json>...

The ground, sharper than the aerial photo: the placed photos taken from high up (observation decks, upper
floors) look down on the crossing at a few centimetres per pixel. Each ground texel takes the median of what
those photos saw, which also thins out people and cars as long as they moved between the photos; where no
high photo saw the ground the aerial photo of ground_ortho.py stays, brought to the same tone.
The poses are a metre or so off at this distance, so the median is taken --align more times, each photo's
ground slid (at most --reach metres) onto the median before; a photo that cannot be matched to it is left out.
Photos from the street are left out (--above, metres over the ground): they see the ground at a grazing
angle, through a crowd. What stands above the ground and is not in the city model (trees, cars, the railway
bridge) is still pressed flat onto it.
Writes ground.jpg, seen.png, model.obj and model.mtl like ground_ortho.py, in local east/north/up metres.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import ground_ortho as go
import photo_guard
import surface_atlas as sa
from geometry_map import to_enu

Image.MAX_IMAGE_PIXELS = None
LUM = np.array([0.2126, 0.7152, 0.0722], np.float32)


def high(cams, ground, above):
    return {k: c for k, c in cams.items() if c["eye"][2] - ground > above}


def affine(src, dst):
    """Least-squares 2D affine map (3, 2) taking src (n, 2) to dst (n, 2)."""
    a = np.hstack([np.asarray(src, float), np.ones((len(src), 1))])
    return np.linalg.lstsq(a, np.asarray(dst, float), rcond=None)[0]


def apply_affine(fit, pts):
    return np.asarray(pts, float) @ fit[:2] + fit[2]


def lay_over(base, seen):
    """seen where it is not NaN, base elsewhere; base is first scaled per channel to the median tone of seen
    over the texels both have."""
    ok = np.isfinite(seen[..., 0])
    if not ok.any():
        return base.copy()
    gain = np.median(seen[ok], axis=0) / np.maximum(np.median(base[ok], axis=0), 1.0)
    return np.where(ok[..., None], seen, base * gain)


def register(moving, fixed, least=15, mask=None, fixed_mask=None, model="similarity"):
    """A warp taking pixels of `fixed` to where the same ground is in `moving` (both (h, w) uint8 grey), and
    how many matched features agree with it. SIFT matches, then RANSAC: the crowd on the crossing differs
    between two photos, the paint on the road does not. model="similarity" gives a 2x3 slide, turn and scale;
    model="homography" a 3x3, which is what a wrongly placed camera really does to a flat ground (plane to
    plane), and so takes in the photos a similarity cannot explain. (None, n) with fewer than `least` inliers:
    better a photo left out than one laid down wrong."""
    import cv2
    sift = cv2.SIFT_create(nfeatures=8000)
    kf, df = sift.detectAndCompute(fixed, None if fixed_mask is None else fixed_mask.astype(np.uint8) * 255)
    km, dm = sift.detectAndCompute(moving, None if mask is None else mask.astype(np.uint8) * 255)
    if df is None or dm is None or len(kf) < 2 or len(km) < 2:
        return None, 0
    good = [m for m, o in (p for p in cv2.BFMatcher().knnMatch(df, dm, k=2) if len(p) == 2)
            if m.distance < 0.8 * o.distance]
    if len(good) < least:
        return None, len(good)
    src = np.float32([kf[m.queryIdx].pt for m in good])
    dst = np.float32([km[m.trainIdx].pt for m in good])
    if model == "homography":
        warp, inl = cv2.findHomography(src, dst, cv2.RANSAC, 2.5)
    else:
        warp, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.5)
    count = 0 if inl is None else int(inl.sum())
    if warp is None or count < least:
        return None, count
    return warp.astype(np.float64), count


def moved(warp, pts):
    """Mean distance (pixels) the points (n, 2) travel under a 2x3 or 3x3 warp."""
    full = np.vstack([warp, [0, 0, 1]]) if warp.shape[0] == 2 else warp
    q = np.c_[pts, np.ones(len(pts))] @ full.T
    return float(np.hypot(*(q[:, :2] / q[:, 2:] - pts).T).mean())


def slid(warp, shape):
    """(pixels the centre of an image of `shape` moves under `warp`, the warp's scale)."""
    h, w = shape
    return float(np.hypot(*(warp @ [w / 2, h / 2, 1] - [w / 2, h / 2]))), float(np.hypot(*warp[:, 0]))


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    pos = [a for a in argv if not a.startswith("--")]
    work, scene_path, base_dir, out = Path(pos[0]), pos[1], Path(pos[2]), Path(pos[3])
    out.mkdir(parents=True, exist_ok=True)
    cx, cy = (float(v) for v in opts.get("centre", "0,0").split(","))
    half, res, z0 = float(opts.get("half", 160)), float(opts.get("res", 0.1)), float(opts.get("z", 0.0))
    n = int(round(2 * half / res))
    xs = cx - half + (np.arange(n) + 0.5) * res
    ys = cy + half - (np.arange(n) + 0.5) * res                    # row 0 is the north edge
    gx, gy = np.meshgrid(xs, ys)
    points = np.stack([gx.ravel(), gy.ravel(), np.full(n * n, z0)], axis=1)
    up = np.array([0.0, 0.0, 1.0])

    # the aerial mosaic of ground_ortho.py, resampled onto this grid (web mercator is affine at this size)
    origin = np.load(work / "buildings.npz")["origin"]
    zoom = int(opts.get("zoom", 18))
    mosaic = np.asarray(Image.open(base_dir / "ground.jpg").convert("RGB")).astype(np.float32)
    tiles = sorted(tuple(int(t) for t in f.stem.split("_")[1:]) for f in (base_dir / "tiles").glob(f"{zoom}_*.jpg"))
    tx0, ty0 = min(t[0] for t in tiles), min(t[1] for t in tiles)
    lon0, lat0 = float(origin[0]), float(origin[1])
    dlat, dlon = 1 / 111320.0, 1 / (111320.0 * math.cos(math.radians(lat0)))
    lonlat = [(lon0 + (cx + a * half) * dlon, lat0 + (cy + b * half) * dlat) for a in (-1, 0, 1) for b in (-1, 0, 1)]
    pix = [((go.tile_of(lon, lat, zoom)[0] - tx0) * 256, (go.tile_of(lon, lat, zoom)[1] - ty0) * 256)
           for lon, lat in lonlat]
    fit = affine(to_enu(lonlat, origin), pix)
    uv = apply_affine(fit, points[:, :2])
    ok = (uv[:, 0] >= 0) & (uv[:, 0] < mosaic.shape[1] - 1) & (uv[:, 1] >= 0) & (uv[:, 1] < mosaic.shape[0] - 1)
    base = np.zeros((n * n, 3), np.float32)
    base[ok] = sa.bilinear(mosaic, uv[ok, 0], uv[ok, 1])
    cams = {}
    for f in pos[4:]:
        cams.update(json.loads(Path(f).read_text()))
    cams = photo_guard.drop_blocked(high(cams, z0, float(opts.get("above", 40))))
    scene = np.load(scene_path)["tris"].astype(float)
    # a photo from behind a window or on a roof deck stands inside the model of its own building: the model's
    # wall or parapet, a metre ahead, would hide the whole ground. Nothing nearer than --near is let to hide it.
    near = float(opts.get("near", 20))
    rounds = int(opts.get("align", 2))
    model = opts.get("model", "similarity")
    step = max(1, int(round(0.2 / res)))
    few = int(opts.get("few", 3))
    to_fine = np.array([[step, 0, (step - 1) / 2], [0, step, (step - 1) / 2], [0, 0, 1.0]])

    def small(im):
        import cv2
        return cv2.resize(im, (n // step, n // step), interpolation=cv2.INTER_AREA)

    ref = None
    for turn in range(rounds + 1):
        # the poses are good to a metre or so at this distance, which doubles every stripe in the median. The
        # first turn takes the photos as placed; each later turn slides every photo's ground onto the median of
        # the turn before, which is ghosted but stands where the photos agree, and the median sharpens.
        stack = sa.TopK(n * n, int(opts.get("keep", 8)))
        used = {}
        for key, cam in cams.items():
            image = np.asarray(photo_guard.open_photo(cam["photo"]).convert("RGB"))
            if image.shape[1] != cam["width"]:
                raise SystemExit(f"{key}: photo is {image.shape[1]} wide, camera says {cam['width']}")
            colours, weights = sa.observe(image, points, up, cam, sa.depth_buffer(scene, cam, near=near))
            used[key] = int((weights > 0).sum())
            note = ""
            if used[key] and ref is not None:
                import cv2
                grey = small((colours @ LUM).reshape(n, n).astype(np.float32)).clip(0, 255).astype(np.uint8)
                mask = small((weights > 0).reshape(n, n).astype(np.float32)) > 0.95
                warp, agree = register(grey, ref[0], mask=mask, fixed_mask=ref[1], model=model)
                if warp is not None:
                    full = np.vstack([warp, [0, 0, 1]]) if warp.shape[0] == 2 else warp
                    yy, xx = np.nonzero(mask)
                    far = moved(full, np.c_[xx, yy][:: max(1, len(yy) // 2000)]) * res * step
                    scale = float(np.sqrt(abs(np.linalg.det(full[:2, :2]))))
                if warp is None:
                    used[key] = 0
                    note = f"(left out: {agree} matches agree)"
                elif far > float(opts.get("reach", 6.0)) or abs(scale - 1) > 0.1:
                    used[key] = 0
                    note = f"(left out: {agree} matches agree on {far:.1f} m, scale {scale:.2f})"
                else:
                    fine = to_fine @ full @ np.linalg.inv(to_fine)
                    flags = cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
                    colours = cv2.warpPerspective(colours.reshape(n, n, 3), fine, (n, n), flags=flags).reshape(-1, 3)
                    solid = cv2.warpPerspective((weights > 0).reshape(n, n).astype(np.float32), fine, (n, n), flags=flags)
                    weights = cv2.warpPerspective(weights.reshape(n, n).astype(np.float32), fine, (n, n), flags=flags)
                    weights = np.where(solid > 0.999, weights, 0).ravel()
                    note = f"(moved {far:.1f} m, {agree} matches agree)"
                    used[key] = int((weights > 0).sum())
            if used[key]:
                stack.add(colours, weights, view=len(used) - 1)
            print("turn", turn, key[-50:], "saw", used[key], "texels", note, flush=True)
        cols, w, v = stack.arrays(views=True)
        gains = sa.exposure_gains(cols, w, v, few=few)
        cols *= gains[np.maximum(v, 0)][..., None].astype(np.float32)
        fused, count = sa.fuse(cols, w, few=few)
        fused[count < few] = np.nan      # one or two photos: whoever stood there stays; the aerial photo is safer
        fused = fused.reshape(n, n, 3)
        ref = (small(np.nan_to_num(fused @ LUM)).clip(0, 255).astype(np.uint8),
               small((count >= few).reshape(n, n).astype(np.float32)) > 0.95)

    ground = lay_over(base.reshape(n, n, 3), fused) * float(opts.get("dim", 1.0))
    Image.fromarray(ground.clip(0, 255).astype(np.uint8)).save(out / "ground.jpg", quality=93)
    Image.fromarray((np.clip(count.reshape(n, n), 0, 5) * 51).astype(np.uint8)).save(out / "seen.png")
    x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half
    (out / "model.obj").write_text("\n".join([
        "mtllib model.mtl", "usemtl ground",
        f"v {x0:.3f} {y0:.3f} {z0:.3f}", "vt 0 0", f"v {x1:.3f} {y0:.3f} {z0:.3f}", "vt 1 0",
        f"v {x1:.3f} {y1:.3f} {z0:.3f}", "vt 1 1", f"v {x0:.3f} {y1:.3f} {z0:.3f}", "vt 0 1",
        "f 1/1 2/2 3/3", "f 1/1 3/3 4/4"]) + "\n")
    (out / "model.mtl").write_text("newmtl ground\nKd 1 1 1\nmap_Kd ground.jpg\n")
    share = float((count >= few).mean())
    (out / "report.json").write_text(json.dumps({"photos": used, "gains": dict(zip(used, np.round(gains, 3).tolist())),
                                                 "seen_share": share, "res_m": res, "size": n}, indent=1))
    print("ground", n, "x", n, "at", res, "m; seen by", few, "or more high photos:", round(share, 3))


if __name__ == "__main__":
    main(sys.argv[1:])
