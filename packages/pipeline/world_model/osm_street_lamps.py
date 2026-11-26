"""Street lamps for a scene as a lamps.json: {"source", "bbox", "lamps": [{"lnglat", "from", "osm", "heading"}]}.

    OVERPASS_URL=<your Overpass> python -m world_model.osm_street_lamps w,s,e,n     prints the file's path

OSM maps few street lamps in Japanese cities (highway=street_lamp nodes), and buildings/street_lights.py needs
PLATEAU's LOD3 sidewalks, which few places have. So the lamps OSM maps are kept ("from": "osm"), and every road
that would be lit gets lamps every `spacing` metres along it, on alternate kerbs, half the road's width plus
0.5 m out from its centre line ("from": "road", with the heading of its arm toward the road); a road lamp within
spacing/2 of a mapped one or of another road lamp is dropped. A one-way way (one carriageway of a dual road) is lit
from its left kerb only, the outer one where traffic keeps left, so no lamp stands in the median.
The width is OSM's width, else lanes x 3 m, else CLASS_WIDTH by the road's class. Tunnels, footways and service
roads get none. A lamp that falls inside a building is the scene builder's to drop (world_model/pp_scene.py casts
a ray up from it). One file per box in the shared cache (shared_cache: osm-street-lamps/).
OSM comes only from the Overpass named by OVERPASS_URL: the public servers are shared and are never called.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path

PLACEMENT = 2           # raise when the placement changes: it is part of the cache key
SPACING = 25.0
LANE = 3.0
CLASS_WIDTH = {"trunk": 16.0, "primary": 14.0, "secondary": 11.0, "tertiary": 8.0, "unclassified": 6.0,
               "residential": 5.0, "living_street": 4.0}
KY = 110950.0


def _width(tags: dict) -> float:
    for key, scale in (("width", 1.0), ("lanes", LANE)):
        try:
            return float(str(tags.get(key, "")).replace("m", "").strip()) * scale
        except ValueError:
            pass
    return CLASS_WIDTH[tags["highway"]]


def _lit_road(tags: dict) -> bool:
    return (tags.get("highway") in CLASS_WIDTH and tags.get("tunnel", "no") == "no"
            and tags.get("covered", "no") == "no")


def _along(points: list[tuple[float, float]], spacing: float, offset: float,
           alternate: bool = True) -> list[tuple[float, float, float]]:
    """A point every `spacing` metres along the polyline, moved `offset` to its left, then right, then left...,
    with the heading (degrees clockwise from north) from it back toward the line. Without `alternate`, every
    point is on the side the sign of `offset` gives (positive: left)."""
    out, carried = [], 0.0                       # carried: distance along the line where the next lamp stands
    walked = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg == 0:
            continue
        ux, uy = (x1 - x0) / seg, (y1 - y0) / seg
        while carried <= walked + seg + 1e-6:
            t = carried - walked
            side = offset if len(out) % 2 == 0 or not alternate else -offset
            heading = math.degrees(math.atan2(uy * side, -ux * side)) % 360.0      # the vector (uy, -ux) * side
            out.append((x0 + ux * t - uy * side, y0 + uy * t + ux * side, round(heading, 1)))
            carried += spacing
        walked += seg
    return out


def from_overpass(elements: list[dict], spacing: float = SPACING) -> list[dict]:
    nodes = {e["id"]: (float(e["lon"]), float(e["lat"])) for e in elements if e.get("type") == "node"}
    mapped = [{"lnglat": list(nodes[e["id"]]), "from": "osm", "osm": e["id"]} for e in elements
              if e.get("type") == "node" and (e.get("tags") or {}).get("highway") == "street_lamp"]
    if not nodes:
        return mapped
    lat0 = sum(lat for _, lat in nodes.values()) / len(nodes)
    lon0 = sum(lon for lon, _ in nodes.values()) / len(nodes)
    kx = 111320.0 * math.cos(math.radians(lat0))

    def to_xy(p):
        return ((p[0] - lon0) * kx, (p[1] - lat0) * KY)

    taken = [to_xy(m["lnglat"]) for m in mapped]
    roads = []
    for e in elements:
        tags = e.get("tags") or {}
        if e.get("type") != "way" or not _lit_road(tags):
            continue
        line = [to_xy(nodes[n]) for n in e.get("nodes", []) if n in nodes]
        offset = _width(tags) / 2 + 0.5
        oneway = tags.get("oneway", "no")
        if oneway in ("yes", "true", "1", "-1"):
            # one carriageway of a dual road: lit from its outer kerb, the left of the traffic (Japan drives on the
            # left), so no lamp stands in the median
            points = _along(line, spacing, -offset if oneway == "-1" else offset, alternate=False)
        else:
            points = _along(line, spacing, offset)
        for x, y, heading in points:
            if all(math.hypot(x - tx, y - ty) >= spacing / 2 for tx, ty in taken):
                taken.append((x, y))                   # a later way's lamp this close to it is the same lamp
                roads.append({"lnglat": [lon0 + x / kx, lat0 + y / KY], "from": "road", "osm": e["id"],
                              "heading": heading})
    return mapped + roads


def _fetch(url: str, query: str) -> dict:
    import urllib.parse
    import urllib.request
    req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": query}).encode(),
                                 headers={"User-Agent": "geo-video-factory-street-lamps/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def lamps_file(bbox: list[float], fetch=None, spacing: float = SPACING) -> Path:
    """The lamps.json of a box (w, s, e, n), from the shared cache or asked once from OVERPASS_URL."""
    from shared_cache import cache_root
    url = os.environ.get("OVERPASS_URL")
    if not url:
        raise SystemExit("set OVERPASS_URL to your own Overpass instance (public servers are not used)")
    key = hashlib.sha256(json.dumps([round(float(v), 6) for v in bbox] + [spacing, PLACEMENT]).encode()).hexdigest()[:16]
    path = cache_root() / "osm-street-lamps" / f"{key}.json"
    if path.exists():
        return path
    w, s, e, n = bbox
    box = f"({s},{w},{n},{e})"
    query = (f'[out:json][timeout:90];(node["highway"="street_lamp"]{box};'
             f'way["highway"~"^({"|".join(CLASS_WIDTH)})$"]{box};);out body;>;out skel qt;')
    doc = {"source": "OpenStreetMap highway=street_lamp and roads (ODbL); road lamps placed at a spacing",
           "bbox": list(bbox), "spacing": spacing, "placement": PLACEMENT,
           "lamps": from_overpass((fetch or _fetch)(url, query).get("elements", []), spacing)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print(lamps_file([float(v) for v in sys.argv[1].split(",")]))
