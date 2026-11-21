"""Recover the camera of a real photo from pixel <-> world point correspondences.

Use only with real photographs (not generated images): the fit assumes the picture is a pinhole
view of the actual scene. Run as a script on a JSON with `width`, `height`, `origin` [lng, lat],
`initial` (camera dict, see blender_geo.project_point), optional `fixed` and
`points`: [{"name", "lngLat", "altitudeM", "pixel": [u, v]}].
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_geo as bg  # noqa: E402

PARAMS = ("x", "y", "z", "tilt", "bearing", "fov", "shift_px", "roll")


def _to_camera(values: dict[str, float]) -> dict[str, Any]:
    return {"location": (values["x"], values["y"], values["z"]), "tilt": values["tilt"],
            "bearing": values["bearing"], "fov": values["fov"], "shift_px": values["shift_px"],
            "roll": values["roll"]}


def _line_distance(p, a, b) -> float:
    """Signed pixel distance of p from the infinite image line through a and b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    return ((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / math.hypot(dx, dy)


def fit_camera(points: Sequence[Sequence[float]], pixels: Sequence[Sequence[float]], width: int, height: int,
               initial: dict[str, Any], fixed: dict[str, float] | None = None,
               verticals: Sequence | None = None, edges: Sequence | None = None) -> tuple[dict[str, Any], float]:
    """Least-squares camera fit; returns the camera and the RMS pixel error.

    - points/pixels: known 3D points (local meters) and where they appear.
    - verticals: image segments [(u, v), (u, v)] of lines that are vertical in the world (building
      edges, sign sides); they fix tilt and roll.
    - edges: {"xy": (x, y), "pixels": [(u, v), (u, v)]} — a vertical building edge at a known plan
      position (e.g. a footprint corner) seen as an image segment; it fixes bearing and position.
    Line terms are pixel distances, so every term is in pixels.
    """
    fixed = dict(fixed or {})
    start = {"x": initial["location"][0], "y": initial["location"][1], "z": initial["location"][2],
             "tilt": initial["tilt"], "bearing": initial["bearing"], "fov": initial["fov"],
             "shift_px": initial.get("shift_px", 0.0), "roll": initial.get("roll", 0.0)}
    free = [name for name in PARAMS if name not in fixed]

    def values_of(vector) -> dict[str, float]:
        values = dict(start, **fixed)
        values.update(zip(free, (float(v) for v in vector)))
        return values

    def residuals(vector):
        camera = _to_camera(values_of(vector))
        out = []
        for point, pixel in zip(points, pixels):
            u, v = bg.project_point(camera, point, width, height)
            out += [u - pixel[0], v - pixel[1]]
        for a, b in verticals or []:
            # The world vertical through a's ray (at the depth where it meets a far vertical) must pass b.
            origin, direction = bg.pixel_ray(camera, a[0], a[1], width, height)
            foot = [origin[i] + direction[i] * 50.0 for i in range(3)]
            top = bg.project_point(camera, (foot[0], foot[1], foot[2] + 10.0), width, height)
            out.append(_line_distance(b, a, top))
        for edge in edges or []:
            x, y = edge["xy"]
            a = bg.project_point(camera, (x, y, 0.0), width, height)
            b = bg.project_point(camera, (x, y, 60.0), width, height)
            out += [_line_distance(p, a, b) for p in edge["pixels"]]
        return out

    result = least_squares(residuals, [start[name] for name in free], xtol=1e-12, ftol=1e-12)
    return _to_camera(values_of(result.x)), math.sqrt(float(np.mean(np.square(result.fun))))


def _view_residuals(camera, view, points3d):
    w, h = view["size"]
    out = []
    for point, pixel in zip(points3d, view["points"]):
        if pixel is None:
            continue
        u, v = bg.project_point(camera, point, w, h)
        out += [u - pixel[0], v - pixel[1]]
    for a, b in view.get("verticals", []):
        origin, direction = bg.pixel_ray(camera, a[0], a[1], w, h)
        foot = [origin[i] + direction[i] * 50.0 for i in range(3)]
        top = bg.project_point(camera, (foot[0], foot[1], foot[2] + 10.0), w, h)
        out.append(_line_distance(b, a, top))
    for edge in view.get("edges", []):
        x, y = edge["xy"]
        a = bg.project_point(camera, (x, y, 0.0), w, h)
        b = bg.project_point(camera, (x, y, 60.0), w, h)
        out += [_line_distance(p, a, b) for p in edge["pixels"]]
    return out


def fit_views(views: dict, initial: dict, fixed: dict, point_guess):
    """Bundle adjustment: several photos' cameras and shared unknown 3D points, solved together.

    views[name] = {"size": (w, h), "points": [pixel or None per shared point], "verticals", "edges"}
    (same meaning as in fit_camera). A street-level view with known footprint edges fixes plan
    position and scale; another view from elsewhere (e.g. high up) fixes the heights.
    Returns ({name: camera}, [3D points], RMS pixel error).
    """
    names = list(views)
    layout = []
    start = []
    for name in names:
        init = initial[name]
        values = {"x": init["location"][0], "y": init["location"][1], "z": init["location"][2],
                  "tilt": init["tilt"], "bearing": init["bearing"], "fov": init["fov"],
                  "shift_px": init.get("shift_px", 0.0), "roll": init.get("roll", 0.0)}
        for param in PARAMS:
            if param not in fixed.get(name, {}):
                layout.append((name, param))
                start.append(values[param])
    n_cam = len(start)
    for p in point_guess:
        start += list(p)

    def unpack(vector):
        cams = {}
        for name in names:
            init = initial[name]
            values = {"x": init["location"][0], "y": init["location"][1], "z": init["location"][2],
                      "tilt": init["tilt"], "bearing": init["bearing"], "fov": init["fov"],
                      "shift_px": init.get("shift_px", 0.0), "roll": init.get("roll", 0.0)}
            values.update(fixed.get(name, {}))
            cams[name] = values
        for (name, param), value in zip(layout, vector[:n_cam]):
            cams[name][param] = float(value)
        pts = [tuple(float(c) for c in vector[n_cam + 3 * i: n_cam + 3 * i + 3]) for i in range(len(point_guess))]
        return {name: _to_camera(v) for name, v in cams.items()}, pts

    def residuals(vector):
        cams, pts = unpack(vector)
        out = []
        for name in names:
            out += _view_residuals(cams[name], views[name], pts)
        return out

    result = least_squares(residuals, start, xtol=1e-12, ftol=1e-12, max_nfev=20000)
    cams, pts = unpack(result.x)
    return cams, pts, math.sqrt(float(np.mean(np.square(result.fun))))


def report(spec: dict[str, Any]) -> dict[str, Any]:
    origin = spec["origin"]
    points, pixels = [], []
    for item in spec["points"]:
        x, y = bg.local_meters(item["lngLat"], origin)
        points.append((x, y, item["altitudeM"]))
        pixels.append(item["pixel"])
    edges = [{"xy": bg.local_meters(e["lngLat"], origin), "pixels": e["pixels"]} for e in spec.get("edges", [])]
    camera, rms = fit_camera(points, pixels, spec["width"], spec["height"], spec["initial"], spec.get("fixed"),
                             verticals=spec.get("verticals"), edges=edges)
    lng = origin[0] + camera["location"][0] / (111_320 * math.cos(math.radians(origin[1])))
    lat = origin[1] + camera["location"][1] / 110_950
    edge_errors = {}
    for e, local in zip(spec.get("edges", []), edges):
        a = bg.project_point(camera, (*local["xy"], 0.0), spec["width"], spec["height"])
        b = bg.project_point(camera, (*local["xy"], 60.0), spec["width"], spec["height"])
        edge_errors[e.get("name", str(e["lngLat"]))] = [round(_line_distance(p, a, b), 1) for p in e["pixels"]]
    return {
        "rmsPx": rms, "eye": [lng, lat, camera["location"][2]], "bearing": camera["bearing"],
        "tilt": camera["tilt"], "fov": camera["fov"], "shiftPx": camera["shift_px"], "roll": camera["roll"],
        "edgeResidualsPx": edge_errors,
        "residualsPx": {item["name"]: [round(a - b, 1) for a, b in
                                       zip(bg.project_point(camera, p, spec["width"], spec["height"]), item["pixel"])]
                        for item, p in zip(spec["points"], points)},
    }


def main() -> None:  # pragma: no cover - thin CLI
    print(json.dumps(report(json.loads(Path(sys.argv[1]).read_text())), ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
