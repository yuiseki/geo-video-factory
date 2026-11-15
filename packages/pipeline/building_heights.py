"""Building height estimates for footprints that come without a height.

Order of evidence, strongest first, and the source is kept with every estimate:

1. a measured OSM `height` tag                      -> 'osm:height'
2. an OSM `building:levels` tag x STORY_M            -> 'osm:levels'
3. the median measured height of buildings of the same GSI structure class and floor-area bin,
   calibrated on PLATEAU buildings nearby when enough of them exist, otherwise PRIOR_HEIGHTS
                                                      -> 'model:<vt_code>'

Axiom: every building is at least one story tall (ONE_STORY_M). One story is the lower bound
of an estimate, not its default.

Model estimates get a small deterministic per-building variation (from the building ID) so a
street of same-class houses does not come out as one flat slab. They are estimates for the
picture; never present them as measured heights.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable

STORY_M = 3.0
ONE_STORY_M = 3.0
# Lower edges of the footprint-area bins in m^2.
AREA_BINS = [0, 30, 60, 120, 250, 600, 2000]
# Starting values per GSI vt_code before calibration (visual starting points, not survey data).
PRIOR_HEIGHTS: dict[str, list[float]] = {
    '3101': [3.0, 5.5, 6.5, 7.0, 8.0, 9.0, 10.0],      # 普通建物: sheds, 2-story houses, low shops
    '3102': [6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0],  # 堅ろう建物: RC apartments, offices, schools
    '3103': [30.0, 30.0, 35.0, 40.0, 45.0, 50.0, 60.0],  # 高層建物
    '3111': [3.0] * 7,                                  # 普通無壁舎: carports, sheds without walls
    '3112': [3.0] * 7,                                  # 堅ろう無壁舎
}


def area_bin(area_m2: float) -> int:
    index = 0
    for i, lower in enumerate(AREA_BINS):
        if area_m2 >= lower:
            index = i
    return index


def footprint_area_m2(ring: list[list[float]]) -> float:
    """Planar area of a lon/lat ring, using a local equirectangular projection."""
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    kx = 111_320.0 * math.cos(lat0)
    ky = 110_950.0
    pts = [(p[0] * kx, p[1] * ky) for p in ring]
    return abs(sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1))) / 2


def calibrate_height_model(samples: Iterable[tuple[Any, float, float]], *, min_samples: int = 8) -> dict[str, Any]:
    """Median measured height per (class, area bin); bins with too few samples keep the prior."""
    groups: dict[tuple[str, int], list[float]] = {}
    for code, area, height in samples:
        if height and height > 0:
            groups.setdefault((str(code), area_bin(area)), []).append(float(height))
    heights = {code: list(values) for code, values in PRIOR_HEIGHTS.items()}
    counts = {code: [0] * len(AREA_BINS) for code in PRIOR_HEIGHTS}
    for (code, index), values in groups.items():
        heights.setdefault(code, list(PRIOR_HEIGHTS['3101']))
        counts.setdefault(code, [0] * len(AREA_BINS))
        counts[code][index] = len(values)
        if len(values) >= min_samples:
            values = sorted(values)
            middle = len(values) // 2
            heights[code][index] = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    return {'heights': heights, 'counts': counts, 'area_bins': AREA_BINS, 'min_samples': min_samples}


def _positive(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        value = float(str(raw).strip().lower().removesuffix('m').strip())
    except ValueError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def estimate_height(properties: dict[str, Any], area_m2: float, model: dict[str, Any], identifier: str) -> tuple[float, str]:
    """Return (height in meters, source of the estimate); never lower than one story."""
    height = _positive(properties.get('height'))
    if height is not None:
        return max(height, ONE_STORY_M), 'osm:height'
    levels = _positive(properties.get('building:levels'))
    if levels is not None:
        return max(levels * STORY_M, ONE_STORY_M), 'osm:levels'
    code = str(properties.get('vt_code') or '3101')
    table = (model.get('heights') or {}).get(code) or PRIOR_HEIGHTS.get(code) or PRIOR_HEIGHTS['3101']
    base = table[area_bin(area_m2)]
    jitter = 0.88 + 0.24 * (int(hashlib.sha256(identifier.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF)
    return max(round(base * jitter, 2), ONE_STORY_M), f'model:{code}'
