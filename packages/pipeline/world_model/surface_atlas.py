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
                   (view_fusion.py, with the other ways of fusing)

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


def texel_quality(weights, texel):
    """How well each texel was seen, 0..1: photo pixels across one texel side in its best photo, capped at 1.

    weights (n, k) are observe()'s pixels per square metre (resolution times foreshortening), k photos per texel;
    sqrt(w) * texel is how many photo pixels one texel spans. A grazing or distant view spans a fraction of a pixel:
    its colour is a smear stretched over the wall, and a renderer should fade it out rather than show it."""
    best = np.max(np.asarray(weights, np.float64), axis=-1)
    return np.clip(np.sqrt(np.maximum(best, 0.0)) * texel, 0.0, 1.0)


# the fusion half lives in view_fusion.py; the old names still work from here
from world_model.view_fusion import (  # noqa: E402,F401
    TopK, exposure_gains, fuse, fuse_by_face, smooth_labels, view_agreement, view_clusters)
