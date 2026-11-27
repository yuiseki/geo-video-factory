"""The check picture of a place found from the roofline: the model's edges drawn on the photo at the found pose.

Every edge within FAR metres is drawn in yellow, and how solid it is says how near it is: an edge within NEAR metres
is solid, beyond that it fades as NEAR / distance down to FAINTEST. Drawn all alike, the streets behind showed
through the buildings in front and the picture could not be read. Far edges are drawn first, so a near one is never
dimmed where they cross. The roofline the search matched is drawn as red dots.
"""
import numpy as np
from PIL import Image, ImageDraw

from geo import skyline_match as sm

NEAR = 60.0          # metres within which an edge is drawn solid
FAR = 900.0          # metres beyond which an edge is not drawn
FAINTEST = 0.15
YELLOW = (255, 230, 0)


def fade(distance):
    """How solid an edge at this distance (metres) is drawn: 1 within NEAR, then NEAR / distance, never under FAINTEST."""
    return np.clip(NEAR / np.maximum(np.asarray(distance, float), 1e-9), FAINTEST, 1.0)


def overlay(full, edges, best, R, bins=720, dots=True, width=1600):
    """full: the photo; edges: (a, b) end points in the local frame; best: the pose; R: its world-to-camera turn."""
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
    order = np.argsort(-d, kind="stable")
    for p, q, alpha in zip((ua[seen] * sc)[order], (ub[seen] * sc)[order], fade(d[order])):
        draw.line([tuple(p), tuple(q)], fill=YELLOW + (int(round(255 * alpha)),), width=1)
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
