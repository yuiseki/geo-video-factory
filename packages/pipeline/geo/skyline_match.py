"""Where a photograph was taken, from the line between the buildings and the sky.

A city model (triangles in east, north, up metres) gives, for any standing point, the elevation of the
roofline in every direction of the compass. A photograph whose roll and pitch are known gives the same
curve over the part of the compass it sees. Comparing the two for every standing point of a grid and every
turn about the vertical needs no initial guess: it is an exhaustive search with a cheap cost.

Angles are degrees. Azimuth is clockwise from north, in bins of 360 / bins degrees; bin i covers
[i, i + 1) * 360 / bins and model values are taken at the bin centres. Numpy only.
"""
import numpy as np


def unique_edges(tris):
    """The edges of the triangles (n, 3, 3), each listed once: two arrays (e, 3) of end points."""
    tris = np.asarray(tris, float)
    a = tris[:, [0, 1, 2]].reshape(-1, 3)
    b = tris[:, [1, 2, 0]].reshape(-1, 3)
    swap = np.zeros(len(a), bool)
    for i in (2, 1, 0):  # order the two ends of every edge by x, then y, then z
        swap = np.where(a[:, i] != b[:, i], a[:, i] > b[:, i], swap)
    a, b = np.where(swap[:, None], b, a), np.where(swap[:, None], a, b)
    key = np.unique(np.round(np.hstack([a, b]) * 1000).astype(np.int64), axis=0, return_index=True)[1]
    return a[key], b[key]


def skyline_edges(a, b, cell=0.01):
    """The edges a-b without the ones that can never be the roofline: an edge that runs under another over the same
    line on the ground (a wall's foot and its diagonal under its top) is lower than it from every eye, in every
    direction. Ground lines are the same when both ends fall in the same `cell` (1 cm: tiles cut apart give one wall
    ends some millimetres apart); vertical edges (a point on the ground) are all kept. On PLATEAU++ this drops 14 %
    of the edges around Ueno-Okachimachi and 40 % around Shibuya, and model_skyline gave the same at every bin of 60
    eyes with them as with all; a bin whose centre grazes a wall's end within the cell may read the wall behind."""
    qa, qb = np.round(a[:, :2] / cell).astype(np.int64), np.round(b[:, :2] / cell).astype(np.int64)
    order = np.lexsort((-b[:, 2], -a[:, 2], qb[:, 1], qb[:, 0], qa[:, 1], qa[:, 0]))   # by ground line, highest first
    a, b, qa, qb = a[order], b[order], qa[order], qb[order]
    first = np.r_[True, (qa[1:] != qa[:-1]).any(1) | (qb[1:] != qb[:-1]).any(1)]
    group = np.cumsum(first) - 1
    low, big = b[:, 2].min(), float(np.ptp(b[:, 2]) + 1.0)
    top = np.maximum.accumulate(b[:, 2] - low + group * big) - group * big + low
    under = np.r_[False, top[:-1] >= b[1:, 2]] & ~first        # an earlier edge of the line is as high at both ends
    keep = ~under | (qa == qb).all(1)
    return a[keep], b[keep]


def model_skyline(a, b, eye, bins=720):
    """The highest elevation of the edges a-b seen from the eye, at the centre of every azimuth bin.
    nan where nothing stands. Edges are enough: on a triangle cut by a vertical plane through the eye the
    elevation is highest at an end of the cut, and the ends lie on the edges."""
    eye = np.asarray(eye, float)
    pa, pb = np.asarray(a, float) - eye, np.asarray(b, float) - eye
    w = 2 * np.pi / bins
    al0 = np.arctan2(pa[:, 0], pa[:, 1])
    turn = (np.arctan2(pb[:, 0], pb[:, 1]) - al0 + np.pi) % (2 * np.pi) - np.pi
    lo = np.where(turn >= 0, al0, al0 + turn)
    span = np.abs(turn)
    k0 = np.ceil(lo / w - 0.5).astype(np.int64)
    k1 = np.floor((lo + span) / w - 0.5).astype(np.int64)
    n = np.where(span < np.pi - 1e-9, np.maximum(k1 - k0 + 1, 0), 0)  # an edge through the eye's vertical is skipped
    out = np.full(bins, -np.inf)
    if n.sum() == 0:
        return np.full(bins, np.nan)
    e = np.repeat(np.arange(len(n)), n)
    k = k0[e] + np.arange(len(e)) - np.repeat(np.cumsum(n) - n, n)
    th = (k + 0.5) * w
    ux, uy = np.sin(th), np.cos(th)
    d = pb[e] - pa[e]
    den = d[:, 0] * uy - d[:, 1] * ux
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    t = np.clip(-(pa[e, 0] * uy - pa[e, 1] * ux) / den, 0.0, 1.0)
    p = pa[e] + t[:, None] * d
    el = np.degrees(np.arctan2(p[:, 2], np.hypot(p[:, 0], p[:, 1])))
    np.maximum.at(out, k % bins, el)
    out[np.isinf(out)] = np.nan
    return out


def pixel_rays(width, height, f, cx, cy, k, R, step=4):
    """Azimuth and elevation of the rays through the centres of step x step blocks of pixels.
    R turns world axes (east, north, up) into camera axes (x right, y down, z forward); f, cx, cy, k are
    the SIMPLE_RADIAL camera of COLMAP. Returns two arrays (height // step, width // step)."""
    u = (np.arange(width // step) + 0.5) * step
    v = (np.arange(height // step) + 0.5) * step
    x, y = ((u - cx) / f)[None, :], ((v - cy) / f)[:, None]
    if k:  # undo x_d = x (1 + k r^2) by fixed-point steps
        xd, yd = np.broadcast_arrays(x, y)
        x, y = xd, yd
        for _ in range(12):
            s = 1 + k * (x * x + y * y)
            x, y = xd / s, yd / s
    R = np.asarray(R, float)
    # each axis of the ray on its own, a row and a column added: four times faster than stacking (x, y, 1) @ R
    ray = [x * R[0, i] + (y * R[1, i] + R[2, i]) for i in range(3)]
    az = np.degrees(np.arctan2(ray[0], ray[1])) % 360
    el = np.degrees(np.arctan2(ray[2], np.hypot(ray[0], ray[1])))
    return az, el


def photo_skyline(az, el, sky, bins=720, el_step=0.25, min_count=4, margin=2):
    """What a photograph says about the roofline, per azimuth bin, from the rays of its pixels (pixel_rays)
    and a mask of the sky. Three arrays in a dict, nan where a bin says nothing of that kind:
    sky    the roofline: the top of the highest cell that is not sky, with sky above it in the frame
    floor  the building leaves the frame at the top: the roofline is at least this high
    ceil   the bin shows only sky: the roofline is at most this high (the bottom of the frame)
    A cell is one azimuth bin wide and el_step high; it counts when it holds min_count pixels, and it is
    sky when at least half of them are. margin is how many sky cells must lie above a roofline.
    Give it tens of pixels per cell: with one or two, the cells that count are scattered and the roofline
    falls into the holes between them."""
    az, el, sky = np.ravel(az), np.ravel(el), np.ravel(sky).astype(bool)
    ne = int(round(180 / el_step))
    ai = np.floor(az / (360 / bins)).astype(np.int64) % bins
    ei = np.clip(np.floor((el + 90) / el_step).astype(np.int64), 0, ne - 1)
    count = np.bincount(ai * ne + ei, minlength=bins * ne).reshape(bins, ne)
    blue = np.bincount(ai * ne + ei, weights=sky, minlength=bins * ne).reshape(bins, ne)
    seen = count >= min_count
    solid = seen & (blue < 0.5 * count)
    any_seen, any_solid = seen.any(1), solid.any(1)
    top = ne - 1 - np.argmax(seen[:, ::-1], axis=1)
    bottom = np.argmax(seen, axis=1)
    roof = ne - 1 - np.argmax(solid[:, ::-1], axis=1)
    edge = (roof + 1) * el_step - 90.0
    cut = top - roof < margin
    nan = np.full(bins, np.nan)
    return dict(sky=np.where(any_solid & ~cut, edge, nan),
                floor=np.where(any_solid & cut, edge, nan),
                ceil=np.where(any_seen & ~any_solid, bottom * el_step - 90.0, nan))


def match_cost(photo, model, tau=5.0, use=("sky", "floor", "ceil"), min_bins=10, empty=0.0, shifts=None, min_sky=0):
    """The cost of every place and every turn: an array (places, shifts).
    photo is the dict of photo_skyline, model is (places, bins) of model_skyline. With the shift s the
    photo's bin b is laid on the model's bin b + s, so s * 360 / bins degrees is how far clockwise the
    photo's assumed heading must be turned. The cost is the mean over the photo's bins of the difference
    in elevation, clipped at tau: two-sided for the roofline, one-sided for floor and ceil. Directions
    where the model has nothing count as elevation empty (the horizon). nan when the photo has fewer
    than min_bins bins to compare, or fewer than min_sky roofline (sky) bins: one-sided floor and ceil bins alone are
    met by any model below them, so a photo without sky (an interior, an alley at night, a statue) would be "placed"
    anywhere at cost 0."""
    model = np.nan_to_num(np.atleast_2d(np.asarray(model, np.float32)), nan=empty)
    places, bins = model.shape
    every = shifts is None
    shifts = np.arange(bins) if every else np.asarray(shifts)
    kinds = [(name, np.flatnonzero(~np.isnan(photo[name]))) for name in use]
    total = sum(len(idx) for _, idx in kinds)
    if total < min_bins or int(np.sum(~np.isnan(photo["sky"]))) < min_sky:
        return np.full((places, len(shifts)), np.nan)
    if every:      # every turn: the model laid twice end to end, so each photo bin reads a plain slice of it
        twice = np.concatenate([model, model], axis=1)
        cost = np.zeros((places, bins))
        part = np.empty((places, bins), np.float32)
        for name, idx in kinds:
            v = np.asarray(photo[name], np.float32)
            for b in idx:
                g = twice[:, b:b + bins]
                if name == "floor":
                    np.subtract(v[b], g, out=part)
                else:
                    np.subtract(g, v[b], out=part)
                if name == "sky":
                    np.abs(part, out=part)
                else:
                    np.maximum(part, 0, out=part)
                cost += np.minimum(part, tau, out=part)
        return cost / total
    cost = np.zeros((places, len(shifts)))
    chunk = max(1, int(5e6 // (len(shifts) * max(len(idx) for _, idx in kinds))))
    for name, idx in kinds:
        if len(idx) == 0:
            continue
        v = np.asarray(photo[name], np.float32)[idx]
        col = (idx[None, :] + shifts[:, None]) % bins
        for i in range(0, places, chunk):
            g = model[i:i + chunk][:, col]
            if name == "sky":
                diff = np.abs(g - v)
            elif name == "floor":
                diff = np.maximum(v - g, 0)
            else:
                diff = np.maximum(g - v, 0)
            cost[i:i + chunk] += np.minimum(diff, tau).sum(-1)
    return cost / total
