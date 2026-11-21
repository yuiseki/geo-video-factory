"""Pure geometry for rendering shot JSON scenes in Blender (no bpy import).

Coordinates are local meters around an origin: X east, Y north, Z up, matching the
Three.js layers of packages/renderer (PLATEAU tiles via ECEF -> ENU, other objects via
the renderer's `localMeters`).
"""
from __future__ import annotations

import math
from typing import Any, Sequence

EARTH_RADIUS = 6378137.0
TILE_SIZE = 512
SEMI_MAJOR = 6378137.0
ECCENTRICITY_SQUARED = 6.69437999014e-3


def meters_per_pixel(zoom: float, latitude: float) -> float:
    """Ground meters per screen pixel of MapLibre (512 px tiles) at the given latitude."""
    return 2 * math.pi * EARTH_RADIUS * math.cos(math.radians(latitude)) / (TILE_SIZE * 2 ** zoom)


def local_meters(point: Sequence[float], origin: Sequence[float]) -> tuple[float, float]:
    """Same approximation as `localMeters` in packages/renderer/src/page/city-timeline.ts."""
    kx = 111_320 * math.cos(math.radians(origin[1]))
    return ((point[0] - origin[0]) * kx, (point[1] - origin[1]) * 110_950)


def maplibre_camera(
    center: Sequence[float],
    zoom: float,
    pitch: float,
    bearing: float,
    fov: float,
    height_px: int,
    origin: Sequence[float],
) -> dict[str, Any]:
    """Blender camera equivalent to a MapLibre camera whose screen center is on the ground (z = 0).

    `fov` is MapLibre's vertical field of view in degrees. Returns the location in local meters,
    an XYZ Euler rotation for a Blender camera (which looks down its local -Z), and the vertical
    field of view in radians.
    """
    distance = 0.5 * height_px / math.tan(math.radians(fov) / 2) * meters_per_pixel(zoom, center[1])
    cx, cy = local_meters(center, origin)
    horizontal = distance * math.sin(math.radians(pitch))
    b = math.radians(bearing)
    return {
        "distance": distance,
        "location": (
            cx - horizontal * math.sin(b),
            cy - horizontal * math.cos(b),
            distance * math.cos(math.radians(pitch)),
        ),
        "rotation_euler": (math.radians(pitch), 0.0, -b),
        "fov_vertical": math.radians(fov),
    }


def interpolate_keys(keys: list[dict[str, Any]], t: float) -> dict[str, Any]:
    """Linear interpolation of shot camera keys at normalized time `t` (clamped)."""
    ordered = sorted(keys, key=lambda key: key["t"])
    if t <= ordered[0]["t"]:
        return dict(ordered[0])
    if t >= ordered[-1]["t"]:
        return dict(ordered[-1])
    for a, b in zip(ordered, ordered[1:]):
        if a["t"] <= t <= b["t"]:
            u = (t - a["t"]) / (b["t"] - a["t"]) if b["t"] > a["t"] else 0.0
            mix = lambda name: a[name] + (b[name] - a[name]) * u  # noqa: E731
            return {
                "t": t,
                "center": [a["center"][i] + (b["center"][i] - a["center"][i]) * u for i in range(2)],
                "zoom": mix("zoom"),
                "pitch": mix("pitch"),
                "bearing": mix("bearing"),
            }
    raise ValueError("unreachable")  # pragma: no cover


def wgs84_ecef(lng_lat_height: Sequence[float]) -> tuple[float, float, float]:
    lon, lat, height = (math.radians(lng_lat_height[0]), math.radians(lng_lat_height[1]), lng_lat_height[2])
    sin_lat = math.sin(lat)
    radius = SEMI_MAJOR / math.sqrt(1 - ECCENTRICITY_SQUARED * sin_lat * sin_lat)
    return (
        (radius + height) * math.cos(lat) * math.cos(lon),
        (radius + height) * math.cos(lat) * math.sin(lon),
        (radius * (1 - ECCENTRICITY_SQUARED) + height) * sin_lat,
    )


def plateau_tile_matrix(rtc: Sequence[float], center: Sequence[float], height_offset: float = 0.0) -> list[list[float]]:
    """4x4 row-major matrix from Blender-imported glTF coords (= ECEF offset from `rtc`) to local ENU.

    Blender's glTF importer maps Y-up (x, y, z) to Z-up (x, -z, y), which is exactly the ECEF offset
    the renderer reconstructs in `gltfVertexToEnu`.
    """
    lam = math.radians(center[0])
    phi = math.radians(center[1])
    rotation = [
        [-math.sin(lam), math.cos(lam), 0.0],
        [-math.sin(phi) * math.cos(lam), -math.sin(phi) * math.sin(lam), math.cos(phi)],
        [math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam), math.sin(phi)],
    ]
    reference = wgs84_ecef([center[0], center[1], 0.0])
    delta = [rtc[i] - reference[i] for i in range(3)]
    translation = [sum(rotation[r][i] * delta[i] for i in range(3)) for r in range(3)]
    translation[2] += height_offset
    return [rotation[r] + [translation[r]] for r in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def facing_euler(bearing: float) -> tuple[float, float, float]:
    """XYZ Euler that turns an XY plane (normal +Z) upright so its front faces `bearing` (deg from north)."""
    return (math.pi / 2, 0.0, math.radians(180 - bearing))


def strict_glb(payload: bytes) -> bytes:
    """Return a GLB that strict loaders accept: drop CESIUM_RTC left in extensionsUsed/Required.

    Older frozen PLATEAU assets kept CESIUM_RTC in `extensionsRequired` after the extension itself
    was stripped (fixed in plateau_3d._strip_cesium_rtc). Other chunks are copied unchanged.
    """
    import json
    import struct

    magic, version, _total = struct.unpack_from("<4sII", payload)
    if magic != b"glTF" or version != 2:
        raise ValueError("payload is not a GLB v2")
    length, kind = struct.unpack_from("<I4s", payload, 12)
    if kind != b"JSON":
        raise ValueError("first GLB chunk must be JSON")
    document = json.loads(payload[20:20 + length].rstrip(b" \t\r\n\0"))
    changed = False
    for key in ("extensionsUsed", "extensionsRequired"):
        if "CESIUM_RTC" in document.get(key, []):
            document[key] = [ext for ext in document[key] if ext != "CESIUM_RTC"]
            if not document[key]:
                document.pop(key)
            changed = True
    if not changed:
        return payload
    raw = json.dumps(document, separators=(",", ":")).encode()
    raw += b" " * ((-len(raw)) % 4)
    rest = payload[20 + length:]
    return struct.pack("<4sII", b"glTF", 2, 20 + len(raw) + len(rest)) + struct.pack("<I4s", len(raw), b"JSON") + raw + rest


def eye_camera(eye: Sequence[float], bearing: float, tilt: float, fov: float, origin: Sequence[float]) -> dict[str, Any]:
    """Blender camera at an eye position `[lng, lat, heightM]` (street-level shots).

    `tilt` follows MapLibre's pitch: 0 looks straight down, 90 looks at the horizon.
    """
    x, y = local_meters(eye, origin)
    return {
        "location": (x, y, float(eye[2])),
        "rotation_euler": (math.radians(tilt), 0.0, -math.radians(bearing)),
        "fov_vertical": math.radians(fov),
    }


def _camera_axes(tilt: float, bearing: float):
    rx, rz = math.radians(tilt), -math.radians(bearing)
    cz, sz = math.cos(rz), math.sin(rz)

    def rot(x: float, y: float, z: float) -> tuple[float, float, float]:
        return (x * cz - y * sz, x * sz + y * cz, z)

    right = rot(1.0, 0.0, 0.0)
    up = rot(0.0, math.cos(rx), math.sin(rx))
    forward = rot(0.0, math.sin(rx), -math.cos(rx))
    return right, up, forward


def project_point(camera: dict[str, Any], point: Sequence[float], width: int, height: int) -> tuple[float, float]:
    """Pixel (u right, v down) of a local-meter point for a camera with location, tilt, bearing,
    vertical fov (deg) and a vertical lens shift in pixels (positive moves the scene down)."""
    right, up, forward = _camera_axes(camera["tilt"], camera["bearing"])
    d = [point[i] - camera["location"][i] for i in range(3)]
    xc = sum(d[i] * right[i] for i in range(3))
    yc = sum(d[i] * up[i] for i in range(3))
    zc = sum(d[i] * forward[i] for i in range(3))
    focal = (height / 2) / math.tan(math.radians(camera["fov"]) / 2)
    return (width / 2 + focal * xc / zc, height / 2 - focal * yc / zc + camera.get("shift_px", 0.0))


def pixel_ray(camera: dict[str, Any], u: float, v: float, width: int, height: int):
    """Origin and unit direction of the ray through pixel (u, v); inverse of `project_point`."""
    right, up, forward = _camera_axes(camera["tilt"], camera["bearing"])
    focal = (height / 2) / math.tan(math.radians(camera["fov"]) / 2)
    a = (u - width / 2) / focal
    b = (height / 2 + camera.get("shift_px", 0.0) - v) / focal
    d = [right[i] * a + up[i] * b + forward[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in d))
    return tuple(camera["location"]), tuple(c / n for c in d)


def sign_box(corners: Sequence[Sequence[float]], camera_location: Sequence[float], depth: float = 1.0) -> dict[str, Any]:
    """Oriented box around a sign from its wall-hit corners (top-left, top-right, bottom-left, bottom-right).

    The box is upright: `axisU` is horizontal along the wall, `normal` points toward the camera.
    """
    tl, tr, bl, br = corners
    center = [sum(c[i] for c in corners) / 4 for i in range(3)]
    along = [((tr[i] - tl[i]) + (br[i] - bl[i])) / 2 for i in range(2)]
    width = math.hypot(*along)
    axis_u = (along[0] / width, along[1] / width, 0.0)
    normal = [axis_u[1], -axis_u[0], 0.0]  # axisU x up
    if sum(normal[i] * (camera_location[i] - center[i]) for i in range(2)) < 0:
        normal = [-normal[0], -normal[1], 0.0]
    half_height = ((tl[2] - bl[2]) + (tr[2] - br[2])) / 4
    return {
        "center": center,
        "axisU": list(axis_u),
        "normal": normal,
        "halfWidth": width / 2,
        "halfHeight": abs(half_height),
        "halfDepth": depth,
    }


def wall_extent_corners(points: Sequence[Sequence[float]], normal: Sequence[float]):
    """Upright rectangle (top-left, top-right, bottom-left, bottom-right) spanning points on one wall."""
    length = math.hypot(normal[0], normal[1])
    axis = (-normal[1] / length, normal[0] / length)
    along = [p[0] * axis[0] + p[1] * axis[1] for p in points]
    mean = [sum(p[i] for p in points) / len(points) for i in range(2)]
    mean_along = mean[0] * axis[0] + mean[1] * axis[1]
    z0, z1 = min(p[2] for p in points), max(p[2] for p in points)

    def corner(a: float, z: float):
        return (mean[0] + (a - mean_along) * axis[0], mean[1] + (a - mean_along) * axis[1], z)

    a0, a1 = min(along), max(along)
    return corner(a0, z1), corner(a1, z1), corner(a0, z0), corner(a1, z0)


def inside_sign_box(box: dict[str, Any], point: Sequence[float]) -> bool:
    d = [point[i] - box["center"][i] for i in range(3)]
    a = sum(d[i] * box["axisU"][i] for i in range(3))
    c = sum(d[i] * box["normal"][i] for i in range(3))
    return abs(a) <= box["halfWidth"] and abs(d[2]) <= box["halfHeight"] and abs(c) <= box["halfDepth"]


def smooth_closed_outline(points, samples_per_edge: int = 6, sharp: set[int] | None = None):
    """Closed Catmull-Rom curve through `points`; edges touching two `sharp` vertices stay straight.

    Returns `len(points) * samples_per_edge` points; sample `i * samples_per_edge` is vertex `i`.
    """
    sharp = sharp or set()
    n = len(points)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = (points[(i + k) % n] for k in (-1, 0, 1, 2))
        straight = i in sharp and (i + 1) % n in sharp
        # A sharp endpoint uses itself as its tangent neighbour, so the curve leaves it straight.
        if i in sharp:
            p0 = p1
        if (i + 1) % n in sharp:
            p3 = p2
        for s in range(samples_per_edge):
            t = s / samples_per_edge
            if straight:
                out.append((p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t))
                continue
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                       + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3)
                for k in range(2)))
    return out


def point_in_polygon(point, polygon, margin: float = 0.0) -> bool:
    """Even-odd test; with `margin`, points within that distance of an edge count as inside."""
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
        if margin > 0:
            dx, dy = x2 - x1, y2 - y1
            length2 = dx * dx + dy * dy or 1e-12
            t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length2))
            if math.hypot(x - (x1 + dx * t), y - (y1 + dy * t)) <= margin:
                return True
    return inside


def outline_vertex_arcs(outline) -> list[float]:
    """Arc length from vertex 0 to each vertex along a closed outline."""
    arcs, total = [], 0.0
    for i in range(len(outline)):
        arcs.append(total)
        total += math.dist(outline[i], outline[(i + 1) % len(outline)])
    return arcs


def _signed_area(outline) -> float:
    return 0.5 * sum(outline[i][0] * outline[(i + 1) % len(outline)][1] - outline[(i + 1) % len(outline)][0] * outline[i][1]
                     for i in range(len(outline)))


def outline_band(outline, s0: float, s1: float, offset: float = 0.1):
    """Points ((x, y), u) of a strip along a closed outline between arc lengths s0 < s1.

    Points sit `offset` meters outside the wall; `u` runs 0 -> 1 from the left to the right of a
    viewer standing outside, so an image laid on the strip reads correctly.
    """
    n = len(outline)
    arcs = outline_vertex_arcs(outline)
    total = arcs[-1] + math.dist(outline[-1], outline[0])
    ccw = _signed_area(outline) > 0

    def edge_normal(i: int):
        (x1, y1), (x2, y2) = outline[i % n], outline[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        return (dy / length, -dx / length) if ccw else (-dy / length, dx / length)

    def at(s: float, vertex: int | None = None):
        s %= total
        i = max(k for k in range(n) if arcs[k] <= s + 1e-9)
        if vertex is not None:
            a, b = edge_normal(vertex - 1), edge_normal(vertex)
            nx, ny = a[0] + b[0], a[1] + b[1]
            length = math.hypot(nx, ny) or 1.0
            nx, ny = nx / length, ny / length
            x, y = outline[vertex % n]
        else:
            length = math.dist(outline[i], outline[(i + 1) % n]) or 1.0
            t = (s - arcs[i]) / length
            (x1, y1), (x2, y2) = outline[i], outline[(i + 1) % n]
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            nx, ny = edge_normal(i)
        return (x + nx * offset, y + ny * offset)

    stops = [(s0, None)]
    for k in range(2 * n):  # vertices inside (s0, s1), allowing the range to wrap once
        s = arcs[k % n] + (total if k >= n else 0.0)
        if s0 + 1e-9 < s < s1 - 1e-9:
            stops.append((s, k % n))
    stops.append((s1, None))
    stops.sort(key=lambda item: item[0])
    out = []
    for s, vertex in stops:
        u = (s - s0) / (s1 - s0)
        out.append((at(s, vertex), u if ccw else 1.0 - u))
    return out
