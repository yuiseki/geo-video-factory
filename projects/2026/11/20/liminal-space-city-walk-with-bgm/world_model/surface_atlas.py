"""The appearance half of the world model: one texture atlas per building, read back from placed photos.

The shape is given (PLATEAU triangles), so the loop runs from the surface. Triangles are grouped into planar
faces, every face gets a rectangular chart at a fixed texel size, and every texel is a point in space. A photo
is an observation of those points: each texel is projected into the photo, kept if the photo really saw it
(inside the frame, facing the camera, and not behind another triangle in the photo's depth buffer), and the
observations are fused. Nothing is detected in the photos.

    planar_faces   triangles -> groups that share a plane
    chart          one group -> texel centres (rows, cols, 3), an inside mask, and the triangle corners in texels
    pack           charts -> positions in one atlas (shelves)
    depth_buffer   all triangles of the scene seen from one camera (clipped at the near plane)
    observe        texel points -> colours from one photo, with a weight (0 where it did not see the texel)
    fuse           weighted median over the photos, or the best view where only a few saw the texel

Cameras: x_cam = Rw @ (x_world - eye), x right, y down, z forward; pixel centres at integer + 0.5.
Lengths are metres, east north up."""
import ctypes
import hashlib
import os
import subprocess
from pathlib import Path

import numpy as np

UP = np.array([0.0, 0.0, 1.0])


def normals(tris):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    length = np.linalg.norm(n, axis=1)
    return n / np.maximum(length, 1e-12)[:, None], 0.5 * length


def planar_faces(tris, angle_deg=4.0, offset=0.25, min_area=1e-4):
    """Lists of triangle indices that lie in one plane (greedy, largest triangles first)."""
    n, area = normals(tris)
    d = np.einsum("ij,ij->i", n, tris[:, 0])
    left = np.where(area > min_area)[0]
    left = left[np.argsort(-area[left])]
    cos = np.cos(np.radians(angle_deg))
    groups = []
    while len(left):
        i = left[0]
        dist = np.abs(np.einsum("ijk,k->ij", tris[left], n[i]) - d[i]).max(axis=1)
        same = (n[left] @ n[i] > cos) & (dist < offset)
        groups.append(left[same])
        left = left[~same]
    return groups


def face_frame(normal):
    """(u, v) on the plane: for a wall, u runs left to right as seen from outside and v runs up."""
    if abs(normal[2]) > 0.95:
        u = np.array([1.0, 0.0, 0.0])
    else:
        u = np.cross(UP, normal)
    u = u / np.linalg.norm(u)
    v = np.cross(normal, u)
    return u, v


def _inside(px, py, a, b, c):
    def edge(p, q):
        return (q[0] - p[0]) * (py - p[1]) - (q[1] - p[1]) * (px - p[0])
    e0, e1, e2 = edge(a, b), edge(b, c), edge(c, a)
    return ((e0 >= 0) & (e1 >= 0) & (e2 >= 0)) | ((e0 <= 0) & (e1 <= 0) & (e2 <= 0))


def chart(tris, texel, pad=1):
    """One planar group as a texture chart. Row 0 is the top (largest v).

    Returns points (rows, cols, 3), mask (rows, cols), normal (3,), corners (n, 3, 2) as (col, row) in texels."""
    n, area = normals(tris)
    normal = (n * area[:, None]).sum(axis=0)
    normal /= np.linalg.norm(normal)
    u, v = face_frame(normal)
    origin = tris.reshape(-1, 3).mean(axis=0)
    uv = np.stack([(tris - origin) @ u, (tris - origin) @ v], axis=-1)
    lo, hi = uv.reshape(-1, 2).min(axis=0), uv.reshape(-1, 2).max(axis=0)
    cols = int(np.ceil((hi[0] - lo[0]) / texel)) + 2 * pad
    rows = int(np.ceil((hi[1] - lo[1]) / texel)) + 2 * pad
    cu = lo[0] + (np.arange(cols) - pad + 0.5) * texel
    cv = hi[1] - (np.arange(rows) - pad + 0.5) * texel
    gu, gv = np.meshgrid(cu, cv)
    mask = np.zeros((rows, cols), bool)
    half = 0.75 * texel
    for a, b, c in uv:
        x0, x1 = np.searchsorted(cu, [min(a[0], b[0], c[0]) - half, max(a[0], b[0], c[0]) + half])
        y0, y1 = np.searchsorted(-cv, [-(max(a[1], b[1], c[1]) + half), -(min(a[1], b[1], c[1]) - half)])
        if x1 > x0 and y1 > y0:
            centre = (a + b + c) / 3
            grow = [centre + (p - centre) * (1 + half / max(np.linalg.norm(p - centre), 1e-6)) for p in (a, b, c)]
            mask[y0:y1, x0:x1] |= _inside(gu[y0:y1, x0:x1], gv[y0:y1, x0:x1], *grow)
    points = origin + gu[..., None] * u + gv[..., None] * v
    corners = np.stack([(uv[..., 0] - lo[0]) / texel + pad, (hi[1] - uv[..., 1]) / texel + pad], axis=-1)
    return points, mask, normal, corners


def pack(sizes, width=4096, gap=2):
    """Shelf packing of (rows, cols) rectangles: (positions [(row, col)], atlas rows)."""
    order = sorted(range(len(sizes)), key=lambda i: -sizes[i][0])
    pos, x, y, shelf = [None] * len(sizes), 0, 0, 0
    for i in order:
        r, c = sizes[i]
        if c > width:
            raise ValueError(f"a chart is {c} texels wide, the atlas is {width}")
        if x + c > width:
            x, y, shelf = 0, y + shelf + gap, 0
        pos[i] = (y, x)
        x, shelf = x + c + gap, max(shelf, r)
    return pos, y + shelf


_LIB = []


def _raster_lib():
    """raster.c as a shared library, built once per source version into the user's cache; None without a compiler."""
    if _LIB:
        return _LIB[0]
    lib = None
    src = Path(__file__).with_name("raster.c")
    try:
        tag = hashlib.sha1(src.read_bytes()).hexdigest()[:12]
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "geo-video-factory"
        so = cache / f"raster_{tag}.so"
        if not so.exists():
            cache.mkdir(parents=True, exist_ok=True)
            subprocess.run(["cc", "-O2", "-shared", "-fPIC", "-o", str(so), str(src), "-lm"], check=True)
        lib = ctypes.CDLL(str(so))
        lib.raster_depth.restype = None
        lib.raster_depth.argtypes = [ctypes.POINTER(ctypes.c_double)] * 3 + [
            ctypes.c_long, ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int]
    except (OSError, subprocess.CalledProcessError):
        lib = None
    _LIB.append(lib)
    return lib


def to_camera(points, cam):
    return (np.asarray(points, float) - np.asarray(cam["eye"])) @ np.asarray(cam["Rw"]).T


def clip_near(tc, near):
    """Triangles in camera space cut at z = near; a triangle crossing the plane becomes one or two."""
    out = [tc[(tc[..., 2] >= near).all(axis=1)]]
    for tri in tc[((tc[..., 2] >= near).any(axis=1)) & ~((tc[..., 2] >= near).all(axis=1))]:
        poly = []
        for p, q in zip(tri, np.roll(tri, -1, axis=0)):
            if p[2] >= near:
                poly.append(p)
            if (p[2] >= near) != (q[2] >= near):
                poly.append(p + (q - p) * (near - p[2]) / (q[2] - p[2]))
        out.append(np.array([[poly[0], poly[i], poly[i + 1]] for i in range(1, len(poly) - 1)]).reshape(-1, 3, 3))
    return np.concatenate(out)


def depth_buffer(tris, cam, scale=0.25, near=0.3, slow=False):
    """Depth (z in camera space, inf where nothing is) of the scene at a fraction of the photo's size.

    The loop over triangles runs in C (raster.c, built on first use next to this file's cache) when a C compiler
    is there; `slow` forces the numpy loop, which is the reference the C one is tested against."""
    fx, fy, cx, cy = cam["params"]
    w, h = int(round(cam["width"] * scale)), int(round(cam["height"] * scale))
    tc = clip_near(to_camera(tris.reshape(-1, 3), cam).reshape(-1, 3, 3), near)
    x = (tc[..., 0] / tc[..., 2] * fx + cx) * scale
    y = (tc[..., 1] / tc[..., 2] * fy + cy) * scale
    keep = (x.max(axis=1) > 0) & (x.min(axis=1) < w) & (y.max(axis=1) > 0) & (y.min(axis=1) < h)
    depth = np.full((h, w), np.inf, np.float32)
    fast = None if slow else _raster_lib()
    if fast is not None:
        xs, ys, zs = (np.ascontiguousarray(a[keep], np.float64) for a in (x, y, tc[..., 2]))
        ptr = ctypes.POINTER(ctypes.c_double)
        fast.raster_depth(xs.ctypes.data_as(ptr), ys.ctypes.data_as(ptr), zs.ctypes.data_as(ptr), len(xs),
                          depth.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), w, h)
        return depth
    for xs, ys, zs in zip(x[keep], y[keep], tc[keep][..., 2]):
        x0, x1 = max(int(np.floor(xs.min())), 0), min(int(np.ceil(xs.max())) + 1, w)
        y0, y1 = max(int(np.floor(ys.min())), 0), min(int(np.ceil(ys.max())) + 1, h)
        if x1 <= x0 or y1 <= y0:
            continue
        px, py = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(den) < 1e-9:
            continue
        l0 = ((ys[1] - ys[2]) * (px - xs[2]) + (xs[2] - xs[1]) * (py - ys[2])) / den
        l1 = ((ys[2] - ys[0]) * (px - xs[2]) + (xs[0] - xs[2]) * (py - ys[2])) / den
        l2 = 1 - l0 - l1
        hit = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        z = 1.0 / (l0 / zs[0] + l1 / zs[1] + l2 / zs[2])
        part = depth[y0:y1, x0:x1]
        part[hit & (z < part)] = z[hit & (z < part)]
    return depth


def bilinear(image, x, y):
    """Colours at pixel coordinates (pixel centres at integer + 0.5), clamped at the border."""
    h, w = image.shape[:2]
    x, y = np.clip(x - 0.5, 0, w - 1.001), np.clip(y - 0.5, 0, h - 1.001)
    x0, y0 = x.astype(int), y.astype(int)
    ax, ay = (x - x0)[..., None], (y - y0)[..., None]
    f = np.float32      # convert only the pixels that are read: the whole photo as float per call is far slower
    return (image[y0, x0].astype(f) * (1 - ax) * (1 - ay) + image[y0, x0 + 1].astype(f) * ax * (1 - ay)
            + image[y0 + 1, x0].astype(f) * (1 - ax) * ay + image[y0 + 1, x0 + 1].astype(f) * ax * ay)


def observe(image, points, normal, cam, depth, scale=0.25, min_cos=0.12, slack=(0.6, 0.02), blocked=None):
    """(colours (..., 3), weight (...)) of surface points in one photo.

    The weight is the number of photo pixels per square metre of surface (resolution times foreshortening);
    it is 0 outside the frame, on faces turned away, behind something else, or where `blocked` (h, w) is set."""
    fx, fy, cx, cy = cam["params"]
    pc = to_camera(points, cam)
    z = pc[..., 2]
    ok = z > 0.3
    zs = np.where(ok, z, 1.0)
    xn, yn = pc[..., 0] / zs, pc[..., 1] / zs
    ux, uy = xn * fx + cx, yn * fy + cy                 # where a straight-line camera would see it (depth buffer)
    k = (cam.get("distortion") or [0.0])[0]
    bend = 1 + k * (xn * xn + yn * yn)                  # COLMAP's SIMPLE_RADIAL
    x, y = xn * bend * fx + cx, yn * bend * fy + cy
    ok &= (x >= 1) & (x < cam["width"] - 1) & (y >= 1) & (y < cam["height"] - 1)
    ray = np.asarray(cam["eye"]) - points
    dist = np.linalg.norm(ray, axis=-1)
    normal = np.asarray(normal)                         # one for all points, or one per point
    cos = np.einsum("...j,...j->...", ray, normal) / np.maximum(dist, 1e-9)
    ok &= cos > min_cos
    dx = np.clip((ux * scale).astype(int), 0, depth.shape[1] - 1)
    dy = np.clip((uy * scale).astype(int), 0, depth.shape[0] - 1)
    ok &= z <= depth[dy, dx] + slack[0] + slack[1] * z
    if blocked is not None:
        ok &= ~blocked[np.clip(y.astype(int), 0, cam["height"] - 1), np.clip(x.astype(int), 0, cam["width"] - 1)]
    weight = np.where(ok, fx * fy * np.clip(cos, 0, 1) / np.maximum(dist, 1e-9) ** 2, 0.0)
    colours = np.zeros(weight.shape + (3,), np.float32)
    colours[ok] = bilinear(image, x[ok], y[ok])
    return colours, weight


def fuse(colours, weights, few=3):
    """One colour per texel from (views, n, 3) and (views, n): the median where `few` or more views saw the
    texel, the sharpest view otherwise. Also returns how many views saw each texel."""
    seen = weights > 0
    count = seen.sum(axis=0)
    out = np.full(colours.shape[1:], np.nan, np.float32)
    idx = np.flatnonzero(count > 0)                         # most of an atlas is empty: work on what was seen
    if len(idx) == 0:
        return out, count
    col, w, n = colours[:, idx], weights[:, idx], count[idx]
    best = np.take_along_axis(col, w.argmax(axis=0)[None, :, None], axis=0)[0]
    stack = np.sort(np.where((w > 0)[..., None], col, np.nan), axis=0)       # NaN sorts last
    lo, hi = ((n - 1) // 2)[None, :, None], (n // 2)[None, :, None]
    median = (np.take_along_axis(stack, lo, axis=0)[0] + np.take_along_axis(stack, hi, axis=0)[0]) / 2
    out[idx] = np.where((n >= few)[:, None], median, best)
    return out, count


def exposure_gains(colours, weights, views, few=3, limit=(0.6, 1.6)):
    """One brightness gain per view, bringing each photo to what the photos agree on.

    The gain is the median, over the texels `few` or more photos saw, of (median luminance / this photo's
    luminance), clipped to `limit`: enough to even out exposure and haze between photos of the same kind of
    light, not enough to turn a night photo into a day one. Views nobody can be compared with keep 1.0.
    """
    lum = np.array([0.2126, 0.7152, 0.0722], np.float32)
    median, count = fuse(colours, weights, few=few)
    ref = median @ lum
    gains = np.ones(int(views.max()) + 1 if views.size else 0)
    ratios = [[] for _ in gains]
    for k in range(len(weights)):
        mine = colours[k] @ lum
        ok = (weights[k] > 0) & (count >= few) & (mine > 8) & (ref > 8)
        order = np.argsort(views[k][ok], kind="stable")
        v, r = views[k][ok][order], (ref[ok] / mine[ok])[order]
        cuts = np.flatnonzero(np.diff(v)) + 1
        for part_v, part_r in zip(np.split(v, cuts), np.split(r, cuts)):
            if len(part_v):
                ratios[int(part_v[0])].append(part_r)
    for i, parts in enumerate(ratios):
        if parts:
            gains[i] = float(np.clip(np.median(np.concatenate(parts)), *limit))
    return gains


def view_agreement(colours, weights, views, close=25.0, sample=200000, seed=0):
    """How alike each pair of photos is where both saw the same texel.

    Returns (share, pairs): share[i, j] is the fraction of the texels both kept where their colours are within
    `close` (mean absolute difference, 0..255), pairs[i, j] how many texels that was. A fraction rather than a
    mean distance: a video screen or one replaced billboard should not make two photos of the same year look
    like strangers.
    """
    n_views = int(views.max()) + 1
    cols = np.arange(weights.shape[1])
    if len(cols) > sample:
        cols = np.random.default_rng(seed).choice(len(cols), sample, replace=False)
    c, w, v = colours[:, cols], weights[:, cols], views[:, cols]
    near, pairs = np.zeros((n_views, n_views)), np.zeros((n_views, n_views))
    for a in range(len(w)):
        for b in range(a + 1, len(w)):
            both = (w[a] > 0) & (w[b] > 0)
            ok = np.abs(c[a][both] - c[b][both]).mean(axis=1) < close
            for i, j in ((v[a][both], v[b][both]), (v[b][both], v[a][both])):
                np.add.at(near, (i, j), ok)
                np.add.at(pairs, (i, j), 1)
    return near / np.maximum(pairs, 1), pairs


def view_clusters(share, pairs, k=2, enough=300):
    """Photos grouped into k sets that look alike (average linkage on 1 - share): the eras of a facade.

    Pairs that share fewer than `enough` texels say nothing and take the mean of the rest. Returns a label per
    view, 0 for the largest set.
    """
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    known = pairs >= enough
    np.fill_diagonal(known, False)
    d = np.where(known, 1 - share, (1 - share)[known].mean() if known.any() else 0.5)
    np.fill_diagonal(d, 0)
    d = (d + d.T) / 2
    if len(d) <= k:
        return np.zeros(len(d), int)
    raw = fcluster(linkage(squareform(d, checks=False), "average"), k, "maxclust")
    order = np.argsort(-np.bincount(raw))
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    return rank[raw]


def smooth_labels(score, pairs, strength=0.7, rounds=6):
    """One view per group, preferring the view the neighbouring groups took.

    score (groups, views) >= 0; pairs (m, 2) are neighbouring groups. Each group starts on its best view and is
    then revisited: a view's worth is log(score / the group's best) + strength x (neighbours on that view), so at
    0.7 a view half as good wins when one more neighbour uses it. Fewer seams, and a sign or a video screen that
    changed between photos comes from one photo instead of a mosaic of several. Views with no score are never taken.
    """
    top = score.max(axis=1, keepdims=True)
    worth = np.where(score > 0, np.log(np.maximum(score, 1e-30) / np.maximum(top, 1e-30)), -np.inf)
    label = worth.argmax(axis=1)
    pairs = np.asarray(pairs, int).reshape(-1, 2)
    if len(pairs) == 0:
        return label
    both = np.concatenate([pairs, pairs[:, ::-1]])
    pull = np.broadcast_to(np.asarray(strength, float), (len(pairs),))   # one strength, or one per pair
    pull = np.concatenate([pull, pull])
    half = np.arange(len(score)) % 2 == 0
    still = 0
    for r in range(2 * rounds):
        votes = np.zeros_like(score, dtype=float)
        np.add.at(votes, (both[:, 0], label[both[:, 1]]), pull)
        # half of the groups move at a time: when all move at once, two neighbours swap views for ever
        turn = half if r % 2 == 0 else ~half
        new = np.where(turn, (worth + votes).argmax(axis=1), label)
        still = still + 1 if (new == label).all() else 0
        label = new
        if still == 2:
            break
    return label


def fuse_by_face(colours, weights, views, face_of, cap=400.0, agree=None, few=3, pairs=None, strength=0.7,
                 changing=None, hold=8.0):
    """One colour per texel, taking each face (or patch of one: `face_of` is any grouping) from as few photos
    as possible.

    A median over photos of different years and standing points blurs what does not sit exactly on the model's
    plane (signs, sashes, anything the coarse model flattens). Here each group ranks the photos by how much of it
    they saw (the sum of their weights, each capped at `cap` pixels per square metre: detail finer than the atlas
    earns nothing), and every texel takes the best-ranked photo among those kept for it.

    `agree` (a colour distance, 0..255) makes the rank also depend on the other photos: a photo's score on a
    group is multiplied by exp(-d / agree), d being its mean distance from the per-texel median where `few` or
    more photos saw the texel. The median is blurred but it is what most photos agree on, so the photo with a
    passer-by, a bus, a different season's sign or a wrong pose on that patch loses to one without.
    `pairs` (neighbouring groups) smooths the choice across groups, see smooth_labels.
    `changing` (a colour distance; needs `agree`) marks the groups whose photos disagree with each other by more
    than that on average: a video screen, a billboard that was replaced. There the median means nothing, so
    agreement is not asked of the photos, and neighbouring changing groups hold on to the same photo `hold` times
    harder: the screen shows one moment instead of a mosaic of several.
    Returns (colours (n, 3), NaN where unseen; the view taken (n), -1 where unseen)."""
    n_views, n_faces = int(views.max()) + 1, int(face_of.max()) + 1
    score = np.zeros((n_faces, max(n_views, 1)))
    seen = weights > 0
    for k in range(len(weights)):
        np.add.at(score, (face_of[seen[k]], views[k][seen[k]]), np.minimum(weights[k][seen[k]], cap))
    if agree:
        median, count = fuse(colours, weights, few=few)
        judged = count >= few
        dist, hits = np.zeros_like(score), np.zeros_like(score)
        for k in range(len(weights)):
            m = seen[k] & judged
            d = np.abs(colours[k][m] - median[m]).mean(axis=1)
            np.add.at(dist, (face_of[m], views[k][m]), d)
            np.add.at(hits, (face_of[m], views[k][m]), 1)
        # a photo nobody can vouch for on this group is treated as an average disagreement, not as perfect
        mean = np.where(hits > 0, dist / np.maximum(hits, 1), float(agree))
        factor = np.exp(-mean / float(agree))
        moving = np.zeros(n_faces, bool)
        if changing:
            moving = dist.sum(axis=1) / np.maximum(hits.sum(axis=1), 1) > float(changing)
            factor[moving] = 1.0
            if pairs is not None and len(pairs):
                pairs = np.asarray(pairs, int).reshape(-1, 2)
                strength = np.where(moving[pairs[:, 0]] & moving[pairs[:, 1]], strength * hold, strength)
        score = score * factor
    if pairs is not None and len(pairs):
        # the smoothed choice wins wherever that photo saw the texel; elsewhere the plain ranking still applies
        label = smooth_labels(score, pairs, strength)
        score = score.copy()
        score[np.arange(n_faces), label] = score.max() * 2 + 1
    rank = np.where(seen, score[face_of[None, :], np.maximum(views, 0)], -1.0)
    pick = rank.argmax(axis=0)
    cols = np.arange(weights.shape[1])
    out = colours[pick, cols].astype(np.float32)
    chosen = views[pick, cols].astype(np.int32)
    none = ~seen.any(axis=0)
    out[none], chosen[none] = np.nan, -1
    return out, chosen


class TopK:
    """The k heaviest observations of each of n texels, taken one view at a time (a full stack of a few hundred
    photos does not fit in memory). `count` is how many views saw each texel at all."""

    def __init__(self, n, k=6):
        self.colours = np.zeros((k, n, 3), np.float32)
        self.weights = np.zeros((k, n), np.float32)
        self.views = np.full((k, n), -1, np.int16)
        self.count = np.zeros(n, np.int32)

    def add(self, colours, weights, view=0):
        weights = np.asarray(weights, np.float32)
        self.count += weights > 0
        slot = self.weights.argmin(axis=0)
        cols = np.arange(len(slot))
        better = weights > self.weights[slot, cols]
        self.weights[slot[better], cols[better]] = weights[better]
        self.colours[slot[better], cols[better]] = np.asarray(colours, np.float32)[better]
        self.views[slot[better], cols[better]] = view

    def arrays(self, views=False):
        return (self.colours, self.weights, self.views) if views else (self.colours, self.weights)
