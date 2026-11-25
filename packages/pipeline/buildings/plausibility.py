"""Buildings that cannot be real, found before they reach a PLATEAU++ scene.

Traps met more than once, each of which made a building tower over a city where nothing is that tall:

- needle: a sliver of a feature (a wall or a stray vertex, about 1 m2 of footprint) 150 m high. Seen in
  PLATEAU Osaka at Namba, and in a filled-in building that took the height of the large OSM outline it lay
  inside (Shibuya Stream, 180 m on a fragment).
- taller than OSM says: a complex extruded whole to the height of its tower. Namba Parks came as one block of
  155 m over 2.5 ha, flat on top all over; OSM gives it 10 levels. Only a block of 5,000 m2 or more whose top
  covers most of its footprint is judged: a complex with a tower standing on part of it (Tokyo Midtown, Shibuya
  Mark City) is real however low the OSM outline around its centre is, and a small tower that disagrees with
  OSM is more often short in OSM. OSM levels are counted at 3.3 m, which undercounts office towers (Parks
  Tower: 30 levels, 158 m), so only a block more than twice as tall and 40 m taller is refused.
- giant slab: 100 m or more over 1.5 ha, flat on top all over.

"top" is the footprint of the part above 80 % of the height (glb_spatial.extract_glb_feature_shapes).

judge() names the trap for one building, implausible() checks every PLATEAU feature against the smallest OSM
building around its centre, and cap_height() keeps a filled-in building from becoming a needle.
"""
from __future__ import annotations

import math
import re
from typing import Any

LEVEL_M = 3.3
MAX_SLENDERNESS = 12.0      # height / sqrt(footprint area); slender real towers are below 7
NEEDLE_MIN_M = 60.0
SLAB_MIN_M, SLAB_MIN_M2 = 100.0, 15000.0
BLOCK_MIN_M2 = 5000.0       # a complex, not a tower
FLAT_TOP = 0.8              # the top covers this share of the footprint: one extruded block


def osm_height(tags: dict[str, Any]) -> float | None:
    """Height from OSM tags: building:levels x 3.3 m first (it is what mappers count), then height."""
    for key, scale in (("building:levels", LEVEL_M), ("height", 1.0)):
        m = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", str(tags.get(key) or ""))
        if m and float(m.group(1)) > 0:
            return float(m.group(1)) * scale
    return None


def judge(shape: dict[str, float], osm_m: float | None) -> str | None:
    """The trap a building of this height and footprint falls into, or None."""
    h, area = float(shape["height"]), max(float(shape["area"]), 1.0)
    block = float(shape.get("top", area)) >= FLAT_TOP * area
    if h >= NEEDLE_MIN_M and h / math.sqrt(area) > MAX_SLENDERNESS:
        return "needle"
    if block and area >= BLOCK_MIN_M2 and osm_m is not None and h > max(2 * osm_m, osm_m + 40):
        return "taller than OSM says"
    if block and h >= SLAB_MIN_M and area >= SLAB_MIN_M2:
        return "giant slab"
    return None


def implausible(shapes: dict[str, dict[str, Any]], osm_features: list[dict[str, Any]]) -> dict[str, str]:
    """{feature id: trap} for the features (lonlat, height, area) that cannot be real."""
    from shapely.geometry import Point, shape as to_shape
    from shapely.strtree import STRtree

    polys, tags = [], []
    for f in osm_features or []:
        if f.get("geometry", {}).get("type") in ("Polygon", "MultiPolygon"):
            g = to_shape(f["geometry"])
            if g.is_valid and not g.is_empty:
                polys.append(g)
                tags.append(f.get("properties") or {})
    tree = STRtree(polys) if polys else None
    found = {}
    for fid, s in shapes.items():
        osm_m = None
        if tree is not None:
            hits = [int(i) for i in tree.query(Point(*s["lonlat"]), predicate="within")]
            if hits:
                osm_m = osm_height(tags[min(hits, key=lambda i: polys[i].area)])
        trap = judge(s, osm_m)
        if trap:
            found[fid] = trap
    return found


def cap_height(height: float, area_m2: float) -> float:
    """A filled-in building no more slender than MAX_SLENDERNESS."""
    return min(height, MAX_SLENDERNESS * math.sqrt(max(area_m2, 1.0)))
