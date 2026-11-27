"""An SfM model near its place on the city model, moved as a whole until its photos' skylines lie on the roofline.

    python -m world_model.sky_refine <cams.json> <scene tris.npz> <out cams.json> [--photos=16] [--radius=300]

sfm_to_world lays the SfM points on the city model's surfaces, which leaves the model's scale and place loose when
the points are few or on one street (the station front of Minowa: scale 1.7 or 2.2, the outlines of the towers off).
The line between the buildings and the sky is what a photo shows most clearly. Here every photo's sky (sky_mask:
the blue reaching down from the top of the frame) gives its skyline along its own rays (skyline_match.photo_skyline,
with the camera's turn), the city model gives the roofline seen from the camera's eye (model_skyline), and the
whole model is turned, shifted and scaled about its centre (apply_delta) to bring the two together (match_cost,
Nelder-Mead from a coarse search over heading and place). The ground is added to the scene as a wide plane, so that
below the buildings is not taken for sky.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from geo import skyline_match as sm

BINS, EL_STEP = 360, 0.5


def sky_mask(rgb: np.ndarray) -> np.ndarray:
    """The clear sky of a photo: bluish, bright pixels connected to the top row (a blue car or sign below the
    buildings is not sky)."""
    from scipy.ndimage import label
    a = np.asarray(rgb, float) / 255.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    blue = (b >= g) & (b > r + 0.08) & (mx > 0.35) & ((mx - mn) / np.maximum(mx, 1e-6) > 0.15)
    white = (mn > 0.78) & (mx - mn < 0.12)                      # thin cloud and the glare near the sun
    cand = blue | white
    lab, _ = label(cand)
    top = set(np.unique(lab[0])) - {0}
    return np.isin(lab, list(top))


def apply_delta(cams: dict, d: np.ndarray) -> dict:
    """The cameras turned (yaw, pitch, roll in degrees, about the world's up, east and north), shifted (metres) and
    scaled (log) about the mean of their eyes."""
    eyes = np.array([c["eye"] for c in cams.values()], float)
    pivot = eyes.mean(axis=0)
    r = Rotation.from_euler("zxy", [-d[0], d[1], d[2]], degrees=True).as_matrix()
    s = float(np.exp(d[6]))
    out = {}
    for k, c in cams.items():
        eye = pivot + s * r @ (np.asarray(c["eye"], float) - pivot) + np.asarray(d[3:6], float)
        out[k] = dict(c, eye=eye.tolist(), Rw=(np.asarray(c["Rw"], float) @ r.T).tolist())
    return out


def _with_ground(tris: np.ndarray, centre, size=2000.0) -> np.ndarray:
    z = float(np.quantile(tris[..., 2], 0.02))
    x, y = centre[0], centre[1]
    g = [[[x - size, y - size, z], [x + size, y - size, z], [x + size, y + size, z]],
         [[x - size, y - size, z], [x + size, y + size, z], [x - size, y + size, z]]]
    return np.concatenate([tris, np.asarray(g, float)])


def _photo_skyline(cam: dict, sky: np.ndarray) -> dict:
    h, w = sky.shape
    s = w / cam["width"]
    fx, fy, cx, cy = (v * s for v in cam["params"])
    k = (cam.get("distortion") or [0.0])[0] if cam.get("distortion") else 0.0
    az, el = sm.pixel_rays(w, h, fx, cx, cy, k, cam["Rw"], step=1)
    return sm.photo_skyline(az, el, sky, bins=BINS, el_step=EL_STEP)


def cost(cams: dict, masks: dict, tris: np.ndarray, edges=None, tau=5.0) -> float:
    """Mean over the photos of how far (degrees, clipped at tau) their skylines lie from the city model's."""
    a, b = edges if edges is not None else sm.unique_edges(tris)
    out = []
    for k, cam in cams.items():
        if k not in masks:
            continue
        photo = _photo_skyline(cam, masks[k])
        model = sm.model_skyline(a, b, cam["eye"], bins=BINS)
        c = sm.match_cost(photo, model[None], tau=tau, shifts=[0], min_bins=20)[0, 0]
        if np.isfinite(c):
            out.append(c)
    return float(np.mean(out)) if out else float("nan")


def refine(cams: dict, masks: dict, tris: np.ndarray, radius: float = 300.0) -> tuple[dict, dict]:
    """(the cameras moved as a whole to fit the skylines, a report with the cost before and after and the delta)."""
    eyes = np.array([c["eye"] for c in cams.values()], float)
    centre = eyes.mean(axis=0)
    near = np.hypot(*(tris.mean(axis=1)[:, :2] - centre[:2]).T) < radius
    edges = sm.unique_edges(_with_ground(tris[near], centre))
    f = lambda d: cost(apply_delta(cams, d), masks, tris, edges)        # noqa: E731
    before = f(np.zeros(7))
    best, best_cost = np.zeros(7), before
    for yaw in (-8, -4, 0, 4, 8):                  # coarse: heading and place, where the surface fit is loosest
        for dx in (-6, 0, 6):
            for dy in (-6, 0, 6):
                d = np.array([yaw, 0, 0, dx, dy, 0, 0], float)
                c = f(d)
                if c < best_cost:
                    best, best_cost = d, c
    simplex = np.array([best] + [best + e for e in np.diag([2.0, 1.0, 1.0, 3.0, 3.0, 1.0, 0.08])])
    res = minimize(f, best, method="Nelder-Mead", options={"initial_simplex": simplex, "maxiter": 400,
                                                           "xatol": 0.05, "fatol": 1e-3})
    d = res.x if res.fun < best_cost else best
    return apply_delta(cams, d), {"before": before, "after": float(min(res.fun, best_cost)), "delta": d.tolist(),
                                  "photos": len(masks)}


def main(argv: list[str]) -> None:
    from PIL import Image
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    src, scene, out = [a for a in argv if not a.startswith("--")][:3]
    cams = json.loads(Path(src).read_text())
    tris = np.load(scene)["tris"].astype(float)
    keys = sorted(cams, key=lambda k: -cams[k].get("sfm_points", 0))[:int(opts.get("photos", 16))]
    masks = {}
    for k in keys:
        img = Image.open(cams[k]["photo"]).convert("RGB")
        small = img.resize((256, round(img.height * 256 / img.width)))
        m = sky_mask(np.asarray(small))
        if m.mean() > 0.02:                        # a photo without sky says nothing here
            masks[k] = m
    fixed, report = refine(cams, masks, tris, float(opts.get("radius", 300)))
    Path(out).write_text(json.dumps(fixed))
    Path(out).with_suffix(".refine.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report))


if __name__ == "__main__":
    main(sys.argv[1:])
