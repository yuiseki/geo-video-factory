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
