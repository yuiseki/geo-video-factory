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

PARAMS = ("x", "y", "z", "tilt", "bearing", "fov", "shift_px")


def _to_camera(values: dict[str, float]) -> dict[str, Any]:
    return {"location": (values["x"], values["y"], values["z"]), "tilt": values["tilt"],
            "bearing": values["bearing"], "fov": values["fov"], "shift_px": values["shift_px"]}


def fit_camera(points: Sequence[Sequence[float]], pixels: Sequence[Sequence[float]], width: int, height: int,
               initial: dict[str, Any], fixed: dict[str, float] | None = None) -> tuple[dict[str, Any], float]:
    """Least-squares camera fit; returns the camera and the RMS pixel error."""
    fixed = dict(fixed or {})
    start = {"x": initial["location"][0], "y": initial["location"][1], "z": initial["location"][2],
             "tilt": initial["tilt"], "bearing": initial["bearing"], "fov": initial["fov"],
             "shift_px": initial.get("shift_px", 0.0)}
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
        return out

    result = least_squares(residuals, [start[name] for name in free], xtol=1e-12, ftol=1e-12)
    return _to_camera(values_of(result.x)), math.sqrt(float(np.mean(np.square(result.fun))))


def report(spec: dict[str, Any]) -> dict[str, Any]:
    origin = spec["origin"]
    points, pixels = [], []
    for item in spec["points"]:
        x, y = bg.local_meters(item["lngLat"], origin)
        points.append((x, y, item["altitudeM"]))
        pixels.append(item["pixel"])
    camera, rms = fit_camera(points, pixels, spec["width"], spec["height"], spec["initial"], spec.get("fixed"))
    lng = origin[0] + camera["location"][0] / (111_320 * math.cos(math.radians(origin[1])))
    lat = origin[1] + camera["location"][1] / 110_950
    return {
        "rmsPx": rms, "eye": [lng, lat, camera["location"][2]], "bearing": camera["bearing"],
        "tilt": camera["tilt"], "fov": camera["fov"], "shiftPx": camera["shift_px"],
        "residualsPx": {item["name"]: [round(a - b, 1) for a, b in
                                       zip(bg.project_point(camera, p, spec["width"], spec["height"]), item["pixel"])]
                        for item, p in zip(spec["points"], points)},
    }


def main() -> None:  # pragma: no cover - thin CLI
    print(json.dumps(report(json.loads(Path(sys.argv[1]).read_text())), ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
