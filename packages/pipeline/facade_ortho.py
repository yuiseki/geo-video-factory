"""Ortho-rectified facade textures from registered photos, driven from geometry that is already known.

The wall is given (an outline of a building from OpenStreetMap or PLATEAU, and a height), so nothing is
detected in the photos. The loop runs from the output: every texel of the wall is a point in space; it is
projected into each photo and the pixel is read there. Perspective undoes itself and the result is at
true scale, without homographies or vanishing points.

    curtain       outline + height -> a grid of 3D points (row 0 at the top, column 0 at the first vertex)
    fit_curtain   move the outline onto the points of a reconstruction (outlines are off by a metre or two)
    fit_relief    how far the real surface stands off that wall, on a coarse grid (set-backs, leaning walls)
    ortho_view    one photo -> the wall's texels as that photo saw them, with a score per texel
    fuse_median   what most views agree on (passers-by and cars drop out)
    fuse_best     each texel from the view that saw it at the highest resolution

Cameras follow COLMAP: x_cam = R @ x_world + t, x right, y down, z forward, SIMPLE_RADIAL distortion, and
pixel (0, 0) covers [0, 1) x [0, 1). Lengths are metres in a local frame with z up.
"""
import numpy as np


def resample(polyline, step):
    """(centres (N, 2), unit directions (N, 2), arc lengths (N,)) of the steps along a polyline."""
    p = np.asarray(polyline, float)
    p = p[np.r_[True, np.hypot(*np.diff(p, axis=0).T) > 1e-9]]
    seg = np.diff(p, axis=0)
    length = np.hypot(seg[:, 0], seg[:, 1])
    cum = np.r_[0.0, np.cumsum(length)]
    s = (np.arange(int(np.floor(cum[-1] / step + 1e-9))) + 0.5) * step
    i = np.clip(np.searchsorted(cum, s, side="right") - 1, 0, len(length) - 1)
    xy = p[i] + ((s - cum[i]) / length[i])[:, None] * seg[i]
    return xy, seg[i] / length[i][:, None], s


def curtain(polyline, z0, height, step):
    """The wall above a polyline as texel centres: (points (rows, cols, 3), outward normals (cols, 2), s).

    The outside of the wall is on the right of the direction of travel (a counter-clockwise outline), so
    the texture reads left to right as seen from outside. Row 0 is the top."""
    xy, d, s = resample(polyline, step)
    rows = int(np.floor(height / step + 1e-9))
    z = z0 + height - (np.arange(rows) + 0.5) * step
    pts = np.empty((rows, len(s), 3))
    pts[..., :2] = xy[None]
    pts[..., 2] = z[:, None]
    return pts, np.c_[d[:, 1], -d[:, 0]], s


def project(points, R, t, f, cx, cy, k=0.0):
    """(pixel coordinates (..., 2), depth (...)). Points behind the camera get NaN."""
    pc = np.asarray(points, float) @ np.asarray(R, float).T + np.asarray(t, float)
    depth = pc[..., 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        x = np.where(depth > 0, pc[..., 0] / depth, np.nan)
        y = np.where(depth > 0, pc[..., 1] / depth, np.nan)
    d = 1.0 + k * (x * x + y * y)
    return np.stack([f * d * x + cx, f * d * y + cy], -1), depth


def sample(image, uv):
    """Bilinear read of an (H, W, C) image: (colours float32 (..., C), valid (...))."""
    h, w = image.shape[:2]
    x, y = uv[..., 0] - 0.5, uv[..., 1] - 0.5
    with np.errstate(invalid="ignore"):
        valid = (x >= 0) & (x <= w - 1) & (y >= 0) & (y <= h - 1)
    x, y = np.where(valid, x, 0.0), np.where(valid, y, 0.0)
    x0, y0 = np.minimum(x.astype(np.int64), w - 2), np.minimum(y.astype(np.int64), h - 2)
    fx, fy = (x - x0).astype(np.float32)[..., None], (y - y0).astype(np.float32)[..., None]
    top = image[y0, x0] * (1 - fx) + image[y0, x0 + 1] * fx
    bottom = image[y0 + 1, x0] * (1 - fx) + image[y0 + 1, x0 + 1] * fx
    return (top * (1 - fy) + bottom * fy).astype(np.float32), valid


def ortho_view(image, pts, normals, R, t, f, cx, cy, k=0.0, min_cos=0.2, rows=256):
    """One photo on the wall: (colours uint8 (rows, cols, 3), valid (rows, cols), score float32).

    The score is the photo's resolution on the wall in pixels per metre along the foreshortened
    direction (f * cos(incidence) / distance); 0 where the photo does not see the texel. Views flatter
    than min_cos are dropped. Nothing checks what stands between the camera and the wall."""
    R, t = np.asarray(R, float), np.asarray(t, float)
    eye = -R.T @ t
    h, w = image.shape[:2]
    colour = np.zeros(pts.shape[:2] + (3,), np.uint8)
    valid = np.zeros(pts.shape[:2], bool)
    score = np.zeros(pts.shape[:2], np.float32)
    for r0 in range(0, pts.shape[0], rows):
        p = pts[r0:r0 + rows]
        to_eye = eye - p
        dist = np.linalg.norm(to_eye, axis=-1)
        cos = (to_eye[..., 0] * normals[:, 0] + to_eye[..., 1] * normals[:, 1]) / dist
        uv, depth = project(p, R, t, f, cx, cy, k)
        with np.errstate(invalid="ignore"):              # the pinhole image too: distortion can fold far points in
            pin = project(p, R, t, f, cx, cy)[0]
            inside = (np.abs(pin[..., 0] - cx) < w) & (np.abs(pin[..., 1] - cy) < h)
        c, ok = sample(image, uv)
        ok &= inside & (cos >= min_cos) & (depth > 0)
        colour[r0:r0 + rows][ok] = np.clip(c[ok][:, :3] + 0.5, 0, 255).astype(np.uint8)
        valid[r0:r0 + rows] = ok
        score[r0:r0 + rows] = np.where(ok, f * cos / dist, 0.0)
    return colour, valid, score


def fuse_median(stack, valid, rows=64):
    """Per-texel median over the views that saw it: (colours uint8 (rows, cols, 3), count (rows, cols))."""
    out = np.zeros(stack.shape[1:], np.uint8)
    count = valid.sum(0)
    for r0 in range(0, stack.shape[1], rows):
        block = stack[:, r0:r0 + rows].astype(np.float32)
        block[~valid[:, r0:r0 + rows]] = np.nan
        seen = count[r0:r0 + rows] > 0
        med = np.zeros(block.shape[1:], np.float32)
        if seen.any():
            med[seen] = np.nanmedian(block[:, seen], axis=0)
        out[r0:r0 + rows] = np.clip(med + 0.5, 0, 255).astype(np.uint8)
    return out, count


def fuse_best(stack, score):
    """Each texel from its highest-scoring view: (colours, index of the view or -1)."""
    which = score.argmax(0)
    out = np.take_along_axis(stack, which[None, ..., None], axis=0)[0]
    unseen = score.max(0) <= 0
    out[unseen] = 0
    return out, np.where(unseen, -1, which)


def fit_curtain(guide, points_xy, step=0.5, reach=4.0, along=1.5, smooth=6.0, min_points=10):
    """Move a guide outline onto the points of a wall: (line (N, 2), offsets (N,), counts (N,)).

    At every step of the guide, the offset is the median distance (positive to the outside) of the points
    within `along` of the station and `reach` of the line. Stations with fewer than min_points take the
    offset of their neighbours; the offsets are then smoothed over `smooth` metres."""
    xy, d, _ = resample(guide, step)
    normal = np.c_[d[:, 1], -d[:, 0]]
    pts = np.asarray(points_xy, float)
    offset = np.full(len(xy), np.nan)
    count = np.zeros(len(xy), int)
    for i in range(len(xy)):
        rel = pts - xy[i]
        a, n = rel @ d[i], rel @ normal[i]
        n = n[(np.abs(a) <= along) & (np.abs(n) <= reach)]
        count[i] = len(n)
        if len(n) >= min_points:
            offset[i] = np.median(n)
    seen = np.isfinite(offset)
    if not seen.any():
        return xy, np.zeros(len(xy)), count
    idx = np.arange(len(xy))
    filled = np.interp(idx, idx[seen], offset[seen])
    sigma = max(smooth / step / 2.355, 1e-6)
    half = int(np.ceil(3 * sigma))
    kernel = np.exp(-0.5 * (np.arange(-half, half + 1) / sigma) ** 2)
    smoothed = np.convolve(np.pad(filled, half, mode="edge"), kernel / kernel.sum(), mode="valid")
    return xy + smoothed[:, None] * normal, smoothed, count


def fit_relief(polyline, points, z0, height, cell_s=2.0, cell_z=4.0, reach=6.0, min_points=8, smooth=1):
    """How far the surface stands outside the wall above a polyline: (offsets (nz, ns), counts); row 0 at the top.

    Each cell of cell_s x cell_z metres takes the median distance of the reconstruction's points in it
    (within `reach` of the wall). Cells with fewer than min_points take the mean of their filled
    neighbours, outwards from the filled ones; `smooth` passes of a 1-2-1 blur follow."""
    pts = np.asarray(points, float).reshape(-1, 3)
    xy, d, s = resample(polyline, cell_s / 4)
    normal = np.c_[d[:, 1], -d[:, 0]]
    ns, nz = max(int(np.ceil(s[-1] / cell_s - 1e-9)), 1), max(int(np.ceil(height / cell_z - 1e-9)), 1)
    relief, count = np.full((nz, ns), np.nan), np.zeros((nz, ns), int)
    if len(pts):
        j = np.concatenate([np.argmin(((pts[i:i + 4096, None, :2] - xy[None]) ** 2).sum(-1), axis=1)
                            for i in range(0, len(pts), 4096)])
        rel = pts[:, :2] - xy[j]
        n, a = (rel * normal[j]).sum(1), (rel * d[j]).sum(1)
        col = np.floor((s[j] + a) / cell_s).astype(int)
        row = np.floor((z0 + height - pts[:, 2]) / cell_z).astype(int)
        ok = (np.abs(n) <= reach) & (np.abs(a) <= cell_s / 4) & (col >= 0) & (col < ns) & (row >= 0) & (row < nz)
        cell = row[ok] * ns + col[ok]
        order = np.argsort(cell, kind="stable")
        ids, start, num = np.unique(cell[order], return_index=True, return_counts=True)
        count.flat[ids] = num
        for c, i0, k in zip(ids, start, num):
            if k >= min_points:
                relief.flat[c] = np.median(n[ok][order[i0:i0 + k]])
    if not np.isfinite(relief).any():
        return np.zeros((nz, ns)), count
    while np.isnan(relief).any():
        pad = np.pad(relief, 1, constant_values=np.nan)
        around = np.stack([pad[:-2, 1:-1], pad[2:, 1:-1], pad[1:-1, :-2], pad[1:-1, 2:]])
        have = np.isfinite(around)
        mean = np.where(have, around, 0.0).sum(0) / np.maximum(have.sum(0), 1)
        relief = np.where(np.isnan(relief) & have.any(0), mean, relief)
    for _ in range(smooth):
        pad = np.pad(relief, 1, mode="edge")
        pad = (pad[:-2] + 2 * pad[1:-1] + pad[2:]) / 4
        relief = (pad[:, :-2] + 2 * pad[:, 1:-1] + pad[:, 2:]) / 4
    return relief, count


def apply_relief(pts, normals, relief, cell_s, cell_z, step):
    """The texel centres of `curtain` moved along the normals by the relief (bilinear between cell centres)."""
    rows, cols = pts.shape[:2]
    r = np.clip((np.arange(rows) + 0.5) * step / cell_z - 0.5, 0, relief.shape[0] - 1)
    c = np.clip((np.arange(cols) + 0.5) * step / cell_s - 0.5, 0, relief.shape[1] - 1)
    r0, c0 = np.minimum(r.astype(int), max(relief.shape[0] - 2, 0)), np.minimum(c.astype(int), max(relief.shape[1] - 2, 0))
    r1, c1 = np.minimum(r0 + 1, relief.shape[0] - 1), np.minimum(c0 + 1, relief.shape[1] - 1)
    fr, fc = (r - r0)[:, None], (c - c0)[None]
    off = (relief[r0][:, c0] * (1 - fr) * (1 - fc) + relief[r0][:, c1] * (1 - fr) * fc
           + relief[r1][:, c0] * fr * (1 - fc) + relief[r1][:, c1] * fr * fc)
    out = pts.copy()
    out[..., :2] += off[..., None] * normals[None]
    return out


def covered_run(count, min_points=10, max_gap=4):
    """(first, last) station of the longest stretch with points, bridging gaps of up to max_gap stations."""
    best, start, last = (0, 0), None, None
    for i, ok in enumerate(np.asarray(count) >= min_points):
        if not ok:
            continue
        if start is None or i - last - 1 > max_gap:
            start = i
        last = i
        if last - start > best[1] - best[0]:
            best = (start, last)
    return best
