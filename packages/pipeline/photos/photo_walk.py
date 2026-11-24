"""Straight walk along a crosswalk through a photo projected on a city model: which photo, which line.

A photo projected from its own eye point reproduces itself from that point. Walking forward along the
photo's axis keeps the frame inside what the photo saw (anything the forward camera sees within its field
of view was nearer the axis from the original eye), so a straight walk needs a photo taken on the
crosswalk, looking along it. Turning or stepping aside shows surfaces the photo never saw.

Photos are level pinhole cameras: {"eye": (x, y, z), "bearing", "pitch", "fov_v" (degrees), "width",
"height"}. Coordinates are local metres, x east, y north, z up; bearings clockwise from north.

Pure functions only (no file or renderer access).
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

EARTH_RADIUS = 6378137.0
DEPTHS = (10.0, 20.0, 40.0, 80.0, 160.0, 320.0)   # metres along each frame ray where coverage is sampled
GRID = (48, 32)                                   # frame rays: columns, rows

# gates of rank_walks: a row "fails" each one it does not meet
MIN_COVERAGE = 0.95     # least covered frame of the walk
MAX_EYE_GAP = 2.0       # m between the photo's eye and the nearest point of the walk line
MAX_EYE_HEIGHT = 4.0    # m above the ground: higher is a bridge, a window or a drone, not a walker
MIN_DETAIL = 1.5        # photo pixels per frame pixel at the start; a walk enlarges the far end further


def bearing(a: Sequence[float], b: Sequence[float]) -> float:
    """Bearing in degrees from point a to point b."""
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1])) % 360


def crosswalks_local(doc: dict[str, Any], origin: Sequence[float]) -> list[dict[str, Any]]:
    """Crosswalks of a crosswalks.json ({"crosswalks": [{"name", "width", "line": [[lon, lat], ...]}]}) as
    {"name", "a", "b", "width"} in metres around origin (lon, lat). Equirectangular on the sphere, the
    same conversion the renderer uses to draw the stripes, so the walk lands on them."""
    kn = EARTH_RADIUS * math.pi / 180
    ke = kn * math.cos(math.radians(origin[1]))
    out = []
    for cw in doc["crosswalks"]:
        a, b = [((lon - origin[0]) * ke, (lat - origin[1]) * kn) for lon, lat in (cw["line"][0], cw["line"][-1])]
        out.append({"name": cw["name"], "a": a, "b": b, "width": float(cw["width"])})
    return out


def _axes(bearing_deg: float, pitch_deg: float):
    b, p = math.radians(bearing_deg), math.radians(pitch_deg)
    fwd = np.array([math.sin(b) * math.cos(p), math.cos(b) * math.cos(p), math.sin(p)])
    right = np.array([math.cos(b), -math.sin(b), 0.0])
    return right, np.cross(right, fwd), fwd


def coverage(photo: dict[str, Any], eye: Sequence[float], bearing_deg: float, pitch_deg: float,
             fov_v: float | None = None, aspect: float | None = None, ground_z: float | None = None,
             depths: Sequence[float] = DEPTHS, grid: Sequence[int] = GRID) -> float:
    """Part (0-1) of a frame that the photo saw. The frame is a level camera at eye; fov_v and aspect
    default to the photo's own. Each frame ray is sampled at `depths`; a sample counts as seen when it
    lies inside the photo's frustum. Samples under ground_z are skipped: the ground is drawn, not
    projected. ground_z defaults to 1.6 m below the photo's eye. Occlusion is ignored (no model needed)."""
    fov_v = photo["fov_v"] if fov_v is None else fov_v
    aspect = photo["width"] / photo["height"] if aspect is None else aspect
    pe = np.asarray(photo["eye"], float)
    ground_z = pe[2] - 1.6 if ground_z is None else ground_z
    right, up, fwd = _axes(bearing_deg, pitch_deg)
    ty = math.tan(math.radians(fov_v) / 2)
    us = (np.arange(grid[0]) + 0.5) / grid[0] * 2 - 1
    vs = (np.arange(grid[1]) + 0.5) / grid[1] * 2 - 1
    uu, vv = np.meshgrid(us * ty * aspect, vs * ty)
    rays = fwd[None, :] + uu.reshape(-1, 1) * right[None, :] + vv.reshape(-1, 1) * up[None, :]
    rays /= np.linalg.norm(rays, axis=1, keepdims=True)
    pts = np.asarray(eye, float)[None, None, :] + np.asarray(depths, float)[None, :, None] * rays[:, None, :]
    pts = pts.reshape(-1, 3)
    pts = pts[pts[:, 2] >= ground_z]
    if not len(pts):
        return 1.0
    pr, pu, pf = _axes(photo["bearing"], photo["pitch"])
    rel = pts - pe[None, :]
    z = rel @ pf
    py = math.tan(math.radians(photo["fov_v"]) / 2) * (1 + 1e-9)
    px = py * photo["width"] / photo["height"]
    seen = (z > 1e-9) & (np.abs(rel @ pr) <= px * z) & (np.abs(rel @ pu) <= py * z)
    return float(seen.mean())


def walk_line(a: Sequence[float], b: Sequence[float], width: float, photo: dict[str, Any],
              margin: float = 0.5) -> dict[str, Any]:
    """The straight line to walk from end a toward end b of a crosswalk `width` wide: parallel to its
    centre line, moved sideways onto the photo's eye as far as the crosswalk allows (`margin` from its
    edge), starting abreast of the eye (clamped to the crosswalk) and ending at b's kerb.
    Returns start, end, bearing, offset (m right of the centre line) and eye_gap (m from the eye to the
    start of the line; 0 when the photo was taken on the crosswalk)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    length = float(np.linalg.norm(b - a))
    d = (b - a) / length
    r = np.array([d[1], -d[0]])                       # to the walker's right
    e = np.asarray(photo["eye"][:2], float) - a
    half = max(0.0, width / 2 - margin)
    offset = float(np.clip(e @ r, -half, half))
    along = float(np.clip(e @ d, 0.0, length))
    start = a + along * d + offset * r
    end = b + offset * r
    return {"start": (float(start[0]), float(start[1])), "end": (float(end[0]), float(end[1])),
            "bearing": bearing(a, b), "offset": offset,
            "eye_gap": float(np.linalg.norm(np.asarray(photo["eye"][:2], float) - start))}


def straight_walk(start: Sequence[float], end: Sequence[float], eye_z: float, pitch: float,
                  speed: float = 1.2, fps: int = 24) -> list[dict[str, float]]:
    """Camera per frame for a walk from start to end at constant speed (m/s), looking along the line."""
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    n = max(1, round(length / speed * fps))
    b = round(bearing(start, end), 6) % 360
    return [{"x": start[0] + (end[0] - start[0]) * i / n, "y": start[1] + (end[1] - start[1]) * i / n,
             "z": eye_z, "bearing": b, "pitch": pitch} for i in range(n + 1)]


def rank_walks(photos: dict[str, dict[str, Any]], crosswalks: Sequence[dict[str, Any]], ground_z: float,
               pitch: float | None = None, frame_height: int | None = None, samples: int = 9,
               margin: float = 0.5) -> list[dict[str, Any]]:
    """Every (photo, crosswalk, direction) rated for a straight walk, best first.
    The frame takes the photo's field of view and aspect (the photo is the render key); pitch defaults to
    the photo's. coverage_min / coverage_mean: `coverage` at `samples` points of the walk. turn: degrees
    between the walk and the photo's axis. detail: photo pixels per frame pixel (frame_height defaults
    to half the photo's). fails: the gates the row misses (module constants); empty means usable."""
    rows = []
    for key, p in photos.items():
        eye_h = p["eye"][2] - ground_z
        frame_h = frame_height or p["height"] / 2
        for cw in crosswalks:
            for direction, (a, b) in (("ab", (cw["a"], cw["b"])), ("ba", (cw["b"], cw["a"]))):
                line = walk_line(a, b, cw["width"], p, margin)
                look = p["pitch"] if pitch is None else pitch
                cov = [coverage(p, (line["start"][0] + (line["end"][0] - line["start"][0]) * t,
                                    line["start"][1] + (line["end"][1] - line["start"][1]) * t, p["eye"][2]),
                                line["bearing"], look, ground_z=ground_z)
                       for t in np.linspace(0.0, 1.0, samples)]
                row = {"photo": key, "crosswalk": cw["name"], "direction": direction,
                       "start": line["start"], "end": line["end"], "bearing": line["bearing"],
                       "walk_m": math.hypot(line["end"][0] - line["start"][0], line["end"][1] - line["start"][1]),
                       "offset": line["offset"], "eye_gap": line["eye_gap"], "eye_height": eye_h,
                       "turn": abs((line["bearing"] - p["bearing"] + 180) % 360 - 180),
                       "coverage_min": min(cov), "coverage_mean": float(np.mean(cov)),
                       "detail": p["height"] / frame_h, "n3d": p.get("n3d")}
                row["fails"] = [name for name, bad in (
                    ("coverage", row["coverage_min"] < MIN_COVERAGE), ("eye_gap", row["eye_gap"] > MAX_EYE_GAP),
                    ("eye_height", eye_h > MAX_EYE_HEIGHT), ("detail", row["detail"] < MIN_DETAIL)) if bad]
                rows.append(row)
    rows.sort(key=lambda r: (len(r["fails"]), -r["coverage_min"], -r["coverage_mean"], r["eye_gap"], -r["walk_m"]))
    return rows
