"""The check picture of a place found from the roofline: the model's edges drawn on the photo at the found pose.

Every edge within FAR metres is drawn in yellow, and how solid it is says how near it is: solid within NEAR
metres, then NEAR / distance. Given the scene's depth at the pose, an edge is drawn so only where it can be seen
(never fainter than SEEN_FAINTEST) and HIDDEN-faint where a nearer wall stands in front of it: drawn all alike, the
far side of a building and the streets behind it showed through its front and the picture could not be read. A far
tower seen whole is still faded, because the facets of a round one are hundreds of edges side by side. Without
the depth every edge fades down to FAINTEST, the far ones drawn first. The roofline the search matched is drawn as red dots.
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from geo import skyline_match as sm

NEAR = 60.0          # metres within which an edge is drawn solid
FAR = 900.0          # metres beyond which an edge is not drawn
FAINTEST = 0.15
SEEN_FAINTEST = 0.4  # with the depth given: the faintest an edge that can be seen is drawn
HIDDEN = 0.1         # how solid an edge is where a nearer wall hides it
YELLOW = (255, 230, 0)
STEP = 3.0           # pixels between the points of an edge that are asked whether they can be seen


def fade(distance):
    """How solid an edge at this distance (metres) is drawn: 1 within NEAR, then NEAR / distance, never under FAINTEST."""
    return np.clip(NEAR / np.maximum(np.asarray(distance, float), 1e-9), FAINTEST, 1.0)


def runs(pa, pb, f, centre, depth):
    """The edge pa-pb (camera space, both in front) cut where it goes behind the depth picture or comes out:
    [(start pixel, end pixel, seen)]. A point is seen when no surface around it is nearer than it by more than
    half a metre and 2 %: an edge lies on its own walls, and at an outline half its pixels are the wall behind."""
    h, w = depth.shape
    ua, ub = pa[:2] / pa[2] * f + centre, pb[:2] / pb[2] * f + centre
    n = int(min(max(np.hypot(*(ub - ua)) / STEP, 1), 2000)) + 1
    t = np.linspace(0.0, 1.0, n)[:, None]
    p = pa + t * (pb - pa)
    u = p[:, :2] / p[:, 2:3] * f + centre
    x, y = np.floor(u[:, 0]).astype(int), np.floor(u[:, 1]).astype(int)
    inside = (x >= 0) & (x < w) & (y >= 0) & (y < h)
    seen = np.zeros(n, bool)
    seen[inside] = p[inside, 2] <= depth[y[inside], x[inside]] * 1.02 + 0.5
    cuts = np.flatnonzero(np.diff(seen)) + 1
    return [(u[i], u[min(j, n - 1)], bool(seen[i])) for i, j in zip(np.r_[0, cuts], np.r_[cuts, n - 1]) if j > i]


def overlay(full, edges, best, R, bins=720, dots=True, width=1600, depth=None):
    """full: the photo; edges: (a, b) end points in the local frame; best: the pose; R: its world-to-camera turn;
    depth: the scene's depth (camera z, inf where nothing is) at the size of the picture drawn, or None."""
    W, H = full.size
    eye = np.array([best["east"], best["north"], best["up"]])
    f = W / 2 / np.tan(np.radians(best["hfov"]) / 2)
    a, b = edges
    dist = np.hypot(*(0.5 * (a + b) - eye)[:, :2].T)
    keep = dist < FAR
    pa, pb = (a[keep] - eye) @ R.T, (b[keep] - eye) @ R.T
    front = (pa[:, 2] > 1) & (pb[:, 2] > 1)
    ua = pa[front, :2] / pa[front, 2:3] * f + [W / 2, H / 2]
    ub = pb[front, :2] / pb[front, 2:3] * f + [W / 2, H / 2]
    seen = ((np.minimum(ua[:, 0], ub[:, 0]) < W) & (np.maximum(ua[:, 0], ub[:, 0]) > 0)
            & (np.minimum(ua[:, 1], ub[:, 1]) < H) & (np.maximum(ua[:, 1], ub[:, 1]) > 0))
    sc = width / W
    canvas = full.resize((width, round(H * sc)), Image.LANCZOS).convert("RGBA")
    lines = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(lines)                   # drawing on the layer replaces, so the nearer edge wins a pixel
    d = dist[keep][front][seen]
    if depth is None:
        order = np.argsort(-d, kind="stable")
        for p, q, alpha in zip((ua[seen] * sc)[order], (ub[seen] * sc)[order], fade(d[order])):
            draw.line([tuple(p), tuple(q)], fill=YELLOW + (int(round(255 * alpha)),), width=1)
    else:
        around = ndimage.maximum_filter(np.asarray(depth, float), 5)
        centre = np.array([width / 2, canvas.size[1] / 2])
        solid = np.maximum(fade(d), SEEN_FAINTEST)
        cut = [(r, alpha) for p, q, alpha in zip(pa[front][seen], pb[front][seen], solid)
               for r in runs(p, q, f * sc, centre, around)]
        cut.sort(key=lambda c: c[1] if c[0][2] else -1.0)      # the hidden first, then the seen from far to near
        for (p, q, is_seen), alpha in cut:
            draw.line([tuple(p), tuple(q)], fill=YELLOW + (int(round(255 * (alpha if is_seen else HIDDEN))),), width=1)
    canvas = Image.alpha_composite(canvas, lines).convert("RGB")
    if dots:
        draw = ImageDraw.Draw(canvas)
        azc = np.radians((np.arange(bins) + 0.5) * 360 / bins)
        el = np.radians(np.nan_to_num(sm.model_skyline(a, b, eye, bins=bins), nan=0.0))
        rays = np.stack([np.sin(azc) * np.cos(el), np.cos(azc) * np.cos(el), np.sin(el)], 1) @ R.T
        ok = rays[:, 2] > 0.1
        for u in rays[ok, :2] / rays[ok, 2:3] * f * sc + [width / 2, H * sc / 2]:
            draw.ellipse([u[0] - 4, u[1] - 4, u[0] + 4, u[1] + 4], fill=(255, 0, 0))
    return canvas
