"""A catalogue of every CC0 or public-domain photo on Wikimedia Commons geotagged inside an area.

    python -m photos.commons_area_catalog <out.jsonl> --bbox=w,s,e,n [--spacing=4] [--boundary=area.geojson]

Commons' search finds files by structured data and place: `haswbstatement:P275=Q6938433` (licence CC0) and
`haswbstatement:P6216=Q19652` (copyright status: public domain), each with `nearcoord:<r>km,<lat>,<lon>`.
The box is covered by circles on a square grid; a circle whose results reach the search's offset limit is
split into four smaller ones instead of being cut short. Each file's licence is then read again from its
own page (fetch_commons_details, "cc0_pd"), so a file whose statement and page disagree is left out.
With --boundary only files inside the polygon (GeoJSON Polygon or MultiPolygon, lon/lat) are kept.

The output has one photo per line, sorted by title: no images are downloaded here.
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.parse
from pathlib import Path

from photos.photo_catalog_sources import fetch_commons_details, fetch_json_with_retry

STATEMENTS = ("haswbstatement:P275=Q6938433", "haswbstatement:P6216=Q19652")
SEARCH_LIMIT = 10000        # CirrusSearch will not page past this offset


class CircleFull(Exception):
    pass


def distance_km(a, b):
    """Great-circle distance between (lon, lat) points."""
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def radius_for(spacing_km):
    """The circle radius that covers a square cell of the grid: half its diagonal, with 5 % to spare for the
    flat-earth degrees of grid_centres."""
    return spacing_km * math.sqrt(2) / 2 * 1.05


def grid_centres(bbox, spacing_km):
    """(lon, lat) cell centres covering the box, spacing_km apart."""
    w, s, e, n = bbox
    dlat = spacing_km / 111.0
    centres = []
    lat = s + dlat / 2
    while lat - dlat / 2 < n:
        dlon = spacing_km / (111.0 * math.cos(math.radians(lat)))
        lon = w + dlon / 2
        while lon - dlon / 2 < e:
            centres.append((round(lon, 5), round(lat, 5)))
            lon += dlon
        lat += dlat
    return centres


def search_circle(centre, radius_km, fetch_fn=None, sleep_fn=time.sleep, max_offset=SEARCH_LIMIT):
    """File titles with either statement within radius_km of centre; CircleFull if a query reaches max_offset."""
    fetch = fetch_fn or fetch_json_with_retry
    lon, lat = centre
    titles = []
    for statement in STATEMENTS:
        # whole metres: a radius like "2.97km" is ignored without a word, and the whole of Commons comes back
        srsearch = f"{statement} nearcoord:{int(round(radius_km * 1000))}m,{lat},{lon} filetype:bitmap"
        offset = 0
        while True:
            params = {"action": "query", "list": "search", "srsearch": srsearch, "srnamespace": "6",
                      "srlimit": "500", "sroffset": str(offset), "srinfo": "totalhits", "format": "json"}
            data = fetch("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params), sleep_fn=sleep_fn)
            total = data.get("query", {}).get("searchinfo", {}).get("totalhits")
            if total is not None and total >= max_offset:
                raise CircleFull(f"{srsearch}: {total} results, more than the search will page through")
            batch = data.get("query", {}).get("search", [])
            titles += [b["title"] for b in batch]
            offset += len(batch)
            if offset >= max_offset:
                raise CircleFull(f"{srsearch}: stopped at {offset}, the search's limit")
            if "continue" not in data or not batch:
                break
            offset = int(data["continue"].get("sroffset", offset))
            sleep_fn(1.0)
        sleep_fn(1.0)
    return titles


def search_area(bbox, spacing_km, fetch_fn=None, sleep_fn=time.sleep, log=print):
    """Every title in the box, splitting full circles."""
    todo = [(c, spacing_km) for c in grid_centres(bbox, spacing_km)]
    found = set()
    while todo:
        (lon, lat), size = todo.pop()
        try:
            got = search_circle((lon, lat), round(radius_for(size), 3), fetch_fn=fetch_fn, sleep_fn=sleep_fn)
        except CircleFull as e:
            log(f"split {lon},{lat} ({size} km): {e}")
            q = size / 4
            dlat, dlon = q / 111.0, q / (111.0 * math.cos(math.radians(lat)))
            todo += [((lon + sx * dlon, lat + sy * dlat), size / 2) for sx in (-1, 1) for sy in (-1, 1)]
            continue
        found.update(got)
        log(f"{lon},{lat} ({size} km): {len(got)} titles, {len(found)} in all, {len(todo)} circles left")
    return sorted(found)


def inside(point, rings):
    """Point (lon, lat) in a polygon given as rings (outer first, then holes), by ray casting."""
    x, y = point
    hit = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                hit = not hit
    return hit


def polygons(geojson):
    geom = geojson.get("geometry", geojson)
    if geojson.get("type") == "FeatureCollection":
        return [p for f in geojson["features"] for p in polygons(f)]
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return list(geom["coordinates"])
    raise ValueError(f"not a polygon: {geom['type']}")


def write_catalog(path, rows):
    unique = {r["title"]: r for r in rows}
    with Path(path).open("w", encoding="utf-8") as f:
        for title in sorted(unique):
            f.write(json.dumps(unique[title], ensure_ascii=False, sort_keys=True) + "\n")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    out = Path([a for a in argv if not a.startswith("--")][0])
    bbox = tuple(float(v) for v in opts["bbox"].split(","))
    titles = search_area(bbox, float(opts.get("spacing", 4)))
    (out.parent / (out.stem + ".titles.txt")).write_text("\n".join(titles) + "\n", encoding="utf-8")
    rows = fetch_commons_details(titles, license_mode="cc0_pd", sleep_fn=lambda s: time.sleep(max(s, 1.0)))
    if "boundary" in opts:
        polys = polygons(json.loads(Path(opts["boundary"]).read_text()))
        rows = [r for r in rows if r.get("coordinates") and any(inside(r["coordinates"], p) for p in polys)]
    write_catalog(out, rows)
    print(f"{len(titles)} titles found, {len(rows)} kept in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
