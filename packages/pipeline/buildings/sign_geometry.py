"""3D shape and placement of signs from real photos.

Given a photo's camera (pipeline/video/camera_fit.py) and a sign's four corners in the photo
(top-left, top-right, bottom-right, bottom-left), the corners are found in 3D either
- on a known wall plane (one photo; walls come from building footprints), or
- by triangulating rays from two or more photos (no wall needed).
Each result carries checks: reprojection error in pixels, corner squareness, planarity.
Coordinates are local meters (x east, y north, z up), as in blender_geo.

CLI: sign_geometry.py <signs.json> <out.json> [--rectify <photo> <dir>]
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parents[1]) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import json
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from buildings import blender_geo as bg  # noqa: E402

Vec = tuple[float, float, float]


def unit(v: Sequence[float]) -> Vec:
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)  # type: ignore[return-value]


def intersect_ray_plane(origin, direction, plane_point, plane_normal) -> Vec | None:
    """Point where a ray meets a plane, or None if parallel or behind the origin."""
    denom = sum(d * n for d, n in zip(direction, plane_normal))
    if abs(denom) < 1e-12:
        return None
    t = sum((p - o) * n for p, o, n in zip(plane_point, origin, plane_normal)) / denom
    if t <= 0:
        return None
    return tuple(o + d * t for o, d in zip(origin, direction))  # type: ignore[return-value]


def triangulate(rays) -> Vec:
    """Least-squares point closest to all rays [(origin, unit direction), ...]."""
    a = np.zeros((3, 3))
    b = np.zeros(3)
    for origin, direction in rays:
        d = np.asarray(direction, float)
        m = np.eye(3) - np.outer(d, d)
        a += m
        b += m @ np.asarray(origin, float)
    return tuple(float(c) for c in np.linalg.solve(a, b))  # type: ignore[return-value]


def wall_plane(a: Sequence[float], b: Sequence[float], toward: Sequence[float]):
    """Vertical plane through footprint edge a-b (local meters), normal facing the point `toward`."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = unit((dy, -dx, 0.0))
    if n[0] * (toward[0] - a[0]) + n[1] * (toward[1] - a[1]) < 0:
        n = (-n[0], -n[1], 0.0)
    return (float(a[0]), float(a[1]), 0.0), n


def choose_wall(origin, direction, buildings):
    """Nearest vertical footprint wall the ray hits within the building's height.

    buildings: [{"name", "outline": [(x, y), ...] closed or open ring in local meters, "heightM"}].
    Returns {"building", "point", "normal", "t"} with the normal facing the ray origin, or None.
    """
    best = None
    for building in buildings:
        ring = list(building["outline"])
        if ring[0] == ring[-1]:
            ring = ring[:-1]
        for i in range(len(ring)):
            a, b = ring[i], ring[(i + 1) % len(ring)]
            point, normal = wall_plane(a, b, origin)
            hit = intersect_ray_plane(origin, direction, point, normal)
            if hit is None or not (0.0 <= hit[2] <= building["heightM"]):
                continue
            ex, ey = b[0] - a[0], b[1] - a[1]
            s = ((hit[0] - a[0]) * ex + (hit[1] - a[1]) * ey) / (ex * ex + ey * ey)
            if not 0.0 <= s <= 1.0:
                continue
            t = math.dist(hit, origin)
            if best is None or t < best["t"]:
                best = {"building": building["name"], "point": point, "normal": normal, "t": t, "edge": [a, b]}
    return best


def _describe(corners: list[Vec], observations) -> dict:
    tl, tr, br, bl = (np.asarray(c, float) for c in corners)
    width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    angles = []
    for p, q, r in ((bl, tl, tr), (tl, tr, br), (tr, br, bl), (br, bl, tl)):
        u, v = p - q, r - q
        angles.append(math.degrees(math.acos(np.clip(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)), -1, 1))))
    pts = np.array([tl, tr, br, bl])
    centroid = pts.mean(0)
    normal = np.linalg.svd(pts - centroid)[2][-1]
    planarity = float(np.abs((pts - centroid) @ normal).max())
    axis_u = (tr - tl + br - bl)
    axis_u[2] = 0.0
    axis_u = axis_u / np.linalg.norm(axis_u)
    face = np.array([axis_u[1], -axis_u[0], 0.0])  # horizontal normal of the upright sign
    camera0 = np.asarray(observations[0][0]["location"], float)
    if face @ (camera0 - centroid) < 0:
        face = -face
    errors = []
    for camera, pixels, width_px, height_px in observations:
        for corner, pixel in zip(corners, pixels):
            u, v = bg.project_point(camera, corner, width_px, height_px)
            errors.append(math.hypot(u - pixel[0], v - pixel[1]))
    return {
        "corners": [tuple(float(c) for c in corner) for corner in corners],
        "widthM": float(width), "heightM": float(height),
        "squarenessDeg": float(max(abs(a - 90) for a in angles)),
        "planarityM": planarity,
        "reprojectionPx": float(max(errors)),
        "box": {"center": [float(c) for c in centroid], "axisU": [float(c) for c in axis_u],
                "normal": [float(c) for c in face], "halfWidth": float(width / 2),
                "halfHeight": float(height / 2), "halfDepth": 1.0},
    }


def sign_from_photo(camera, corners_px, width: int, height: int, wall) -> dict:
    """Corners on a wall plane (point, normal) from one photo."""
    corners = []
    for u, v in corners_px:
        origin, direction = bg.pixel_ray(camera, u, v, width, height)
        hit = intersect_ray_plane(origin, direction, wall[0], wall[1])
        if hit is None:
            raise ValueError(f"corner ({u}, {v}) does not hit the wall")
        corners.append(hit)
    return _describe(corners, [(camera, corners_px, width, height)])


def rectangle_plane(camera, corners_px, width: int, height: int):
    """Orientation of an upright rectangular sign from its image quad (TL, TR, BR, BL).

    The top and bottom edges are parallel in 3D, so the planes through the camera and each edge meet
    along the sign's horizontal direction (its vanishing direction). Assuming the sign stands upright,
    that direction is made horizontal and the normal is horizontal and perpendicular to it, facing the camera.
    """
    rays = [np.asarray(bg.pixel_ray(camera, u, v, width, height)[1]) for u, v in corners_px]
    tl, tr, br, bl = rays
    direction = np.cross(np.cross(tl, tr), np.cross(bl, br))
    direction[2] = 0.0
    direction /= np.linalg.norm(direction)
    if direction @ (tr - tl) < 0:  # point from left to right as seen
        direction = -direction
    normal = np.array([direction[1], -direction[0], 0.0])
    if normal @ (tl + br) > 0:  # face back toward the camera
        normal = -normal
    return tuple(float(c) for c in direction), tuple(float(c) for c in normal)


def sign_from_rectangle(camera, corners_px, width: int, height: int, anchor) -> dict:
    """Upright sign whose orientation comes from its own quad; `anchor` (plane) only fixes the depth."""
    _axis, normal = rectangle_plane(camera, corners_px, width, height)
    cu = sum(c[0] for c in corners_px) / 4
    cv = sum(c[1] for c in corners_px) / 4
    origin, direction = bg.pixel_ray(camera, cu, cv, width, height)
    centre = intersect_ray_plane(origin, direction, anchor[0], anchor[1])
    if centre is None:
        raise ValueError("centre ray misses the anchor plane")
    return sign_from_photo(camera, corners_px, width, height, (centre, normal))


def sign_from_photos(views, width: int, height: int) -> dict:
    """Corners triangulated from two or more photos: views = [(camera, corners_px), ...]."""
    corners = []
    for k in range(4):
        rays = [bg.pixel_ray(camera, *pixels[k], width, height) for camera, pixels in views]
        corners.append(triangulate(rays))
    return _describe(corners, [(camera, pixels, width, height) for camera, pixels in views])


def perspective_coeffs(src_corners, out_w: int, out_h: int):
    """PIL Image.transform(PERSPECTIVE) coefficients mapping an out_w x out_h rectangle to src corners."""
    dst = [(0, 0), (out_w - 1, 0), (out_w - 1, out_h - 1), (0, out_h - 1)]
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src_corners):
        rows.append([x, y, 1, 0, 0, 0, -x * u, -y * u])
        rows.append([0, 0, 0, x, y, 1, -x * v, -y * v])
        rhs += [u, v]
    return tuple(float(c) for c in np.linalg.solve(np.array(rows, float), np.array(rhs, float)))


def _camera(fit: dict, origin) -> dict:
    x, y = bg.local_meters(fit["eye"], origin)
    return {"location": (x, y, fit["eye"][2]), "tilt": fit["tilt"], "bearing": fit["bearing"],
            "fov": fit["fov"], "shift_px": fit.get("shiftPx", 0.0)}


def run(spec: dict) -> dict:  # pragma: no cover - glue around the tested functions
    origin = spec["origin"]
    photos = {name: {"camera": _camera(p["fit"], origin), "size": p["size"]} for name, p in spec["photos"].items()}
    out = []
    for sign in spec["signs"]:
        views = [(photos[o["photo"]]["camera"], o["corners"]) for o in sign["observations"]]
        w, h = photos[sign["observations"][0]["photo"]]["size"]
        if len(views) >= 2:
            result = sign_from_photos(views, w, h)
        elif "wall" in sign:
            a, b = (bg.local_meters(p, origin) for p in sign["wall"])
            result = sign_from_photo(views[0][0], views[0][1], w, h, wall_plane(a, b, views[0][0]["location"]))
        else:
            camera, corners = views[0]
            cu = sum(c[0] for c in corners) / 4
            cv = sum(c[1] for c in corners) / 4
            ray = bg.pixel_ray(camera, cu, cv, w, h)
            buildings = [{"name": b["name"], "heightM": b["heightM"],
                          "outline": [bg.local_meters(p, origin) for p in b["outline"]]} for b in spec["buildings"]]
            wall = choose_wall(ray[0], ray[1], buildings)
            if wall is None:
                print(f"{sign['name']}: no building wall behind the sign, skipped")
                continue
            # Signs stand slightly proud of the facade.
            n = wall["normal"]
            offset = sign.get("offsetM", 0.3)
            plane = (tuple(p + c * offset for p, c in zip(wall["point"], n)), n)
            if sign.get("orientation", "quad") == "quad":
                result = sign_from_rectangle(camera, corners, w, h, plane)
            else:
                result = sign_from_photo(camera, corners, w, h, plane)
            result["building"] = wall["building"]
            # How far the quad's own orientation is from the footprint wall (camera or footprint error).
            cosine = abs(sum(a * b for a, b in zip(result["box"]["normal"], n)))
            result["wallAngleDeg"] = math.degrees(math.acos(min(1.0, cosine)))
        kx = 111_320 * math.cos(math.radians(origin[1]))
        result["cornersLngLatAlt"] = [[origin[0] + c[0] / kx, origin[1] + c[1] / 110_950, c[2]] for c in result["corners"]]
        result["name"] = sign["name"]
        out.append(result)
    return {"origin": origin, "signs": out}


def main() -> None:  # pragma: no cover - thin CLI
    spec = json.loads(Path(sys.argv[1]).read_text())
    result = run(spec)
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False, indent=1))
    if "--rectify" in sys.argv:
        from PIL import Image

        i = sys.argv.index("--rectify")
        photo, out_dir = Image.open(sys.argv[i + 1]).convert("RGB"), Path(sys.argv[i + 2])
        out_dir.mkdir(parents=True, exist_ok=True)
        for sign, s in zip(spec["signs"], result["signs"]):
            corners = sign["observations"][0]["corners"]
            ow = 400
            oh = max(8, round(ow * s["heightM"] / s["widthM"]))
            flat = photo.transform((ow, oh), Image.PERSPECTIVE, perspective_coeffs(corners, ow, oh), Image.BICUBIC)
            flat.save(out_dir / f"{s['name']}.png")
    for s in result["signs"]:
        print(f"{s['name']}: {s['widthM']:.2f} x {s['heightM']:.2f} m, bottom {min(c[2] for c in s['corners']):.1f} m, "
              f"reproj {s['reprojectionPx']:.1f} px, square {s['squarenessDeg']:.1f} deg, "
              f"vs wall {s.get('wallAngleDeg', 0):.0f} deg, on {s.get('building', '-')}")


if __name__ == "__main__":  # pragma: no cover
    main()
