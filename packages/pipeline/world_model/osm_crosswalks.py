"""OpenStreetMap crossings as a crosswalks.json: {"source", "crosswalks": [{"name", "osm", "width", "line"}]}.

    OVERPASS_URL=<your Overpass> python -m world_model.osm_crosswalks w,s,e,n     prints the file's path

Ways tagged footway=crossing whose crossing is marked (zebra, marked, traffic_signals, uncontrolled, or
crossing:markings set and not "no") become a line from their first to their last node, with OSM's width or
DEFAULT_WIDTH; unmarked crossings have no paint to draw. The scene builders draw the zebra bars of each line
(buildings/blender_geo.crosswalk_stripes). One file per box in the shared cache (shared_cache: osm-crosswalks/).
OSM comes only from the Overpass named by OVERPASS_URL: the public servers are shared and are never called.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_WIDTH = 4.0
MARKED = {"zebra", "marked", "traffic_signals", "uncontrolled"}


def _marked(tags: dict) -> bool:
    markings = tags.get("crossing:markings")
    if markings:
        return markings != "no"
    return tags.get("crossing") in MARKED or tags.get("crossing_ref") == "zebra"


def from_overpass(elements: list[dict]) -> list[dict]:
    nodes = {e["id"]: [float(e["lon"]), float(e["lat"])] for e in elements if e.get("type") == "node"}
    out = []
    for e in elements:
        tags = e.get("tags") or {}
        if e.get("type") != "way" or tags.get("footway") != "crossing" or not _marked(tags):
            continue
        ends = [nodes[n] for n in e.get("nodes", []) if n in nodes]
        if len(ends) < 2 or ends[0] == ends[-1]:
            continue
        try:
            width = float(str(tags.get("width", "")).replace("m", "").strip())
        except ValueError:
            width = DEFAULT_WIDTH
        out.append({"name": f"way/{e['id']}", "osm": [e["id"]], "width": width, "line": [ends[0], ends[-1]]})
    return out


def _fetch(url: str, query: str) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": query}).encode(),
                                 headers={"User-Agent": "geo-video-factory-crosswalks/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def crosswalks_file(bbox: list[float], fetch=None) -> Path:
    """The crosswalks.json of a box (w, s, e, n), from the shared cache or asked once from OVERPASS_URL."""
    from shared_cache import cache_root
    url = os.environ.get("OVERPASS_URL")
    if not url:
        raise SystemExit("set OVERPASS_URL to your own Overpass instance (public servers are not used)")
    key = hashlib.sha256(json.dumps([round(float(v), 6) for v in bbox]).encode()).hexdigest()[:16]
    path = cache_root() / "osm-crosswalks" / f"{key}.json"
    if path.exists():
        return path
    w, s, e, n = bbox
    query = f'[out:json][timeout:90];way["footway"="crossing"]({s},{w},{n},{e});out body;>;out skel qt;'
    doc = {"source": "OpenStreetMap footway=crossing, marked (ODbL)", "bbox": list(bbox),
           "crosswalks": from_overpass((fetch or _fetch)(url, query).get("elements", []))}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print(crosswalks_file([float(v) for v in sys.argv[1].split(",")]))
