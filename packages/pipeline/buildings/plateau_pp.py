"""PLATEAU++: PLATEAU's own buildings and textures, synthesized only where PLATEAU has none.

    OVERPASS_URL=<your Overpass> python -m buildings.plateau_pp [<out dir>] --bbox=w,s,e,n
        [--tileset=<PLATEAU 3D Tiles tileset.json>] [--gsi-cache=<dir>] [--seed=plateau-pp]

Since 0.3.0 PLATEAU++ is kept once per tile and shared by every box (buildings.pp_tiles): a box is its manifest and
links into tmp/.cache/plateau-pp/v<PLATEAU_PP_VERSION>/ (plateau/ per PLATEAU tile, proxy/ per GSI z16 tile).
Without an output directory the box goes to boxes/<key>/ there (cached()) and its path is printed; with one, the
manifest and links are written there. A box costs only the tiles no box asked for before.

Per tile, whatever box asks for it:
1. PLATEAU's tile with its own textures, at 2048 px wherever it lies.
2. Buildings that cannot be real are taken out of it (plausibility: needles, complexes extruded to their tower's
   height, giant slabs; OSM within CONTEXT_M of the tile) and listed as removed_buildings.
3. Its untextured buildings get a wall colour from their ID and height (city_proxy.wall_hex) and the GSI photo
   (z18) of the tile's region on their roofs, baked in (pp_bake).
4. Every GSI footprint PLATEAU does not model, including the ones step 2 freed, becomes a filled-in building, kept
   per z16 tile (the footprints whose centre lies in it): on the GSI DEM, OSM building:levels before height,
   otherwise a height calibrated on the PLATEAU buildings of its JIS mesh cell (cell_heights). Filled-in tiles are
   written as ECEF offsets from their own RTC centre, like PLATEAU's (enu_rtc).

OSM comes only from the Overpass named by OVERPASS_URL: the public servers are shared and are never called.
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


TOKYO_2025 = "https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13-bldg-lod2-texture-2025/tileset.json"
PLATEAU_PP_VERSION = "0.3.0"   # raise when a change alters what a build looks like: cached builds live under it


def overpass_endpoint() -> str:
    url = os.environ.get("OVERPASS_URL")
    if not url:
        raise SystemExit("set OVERPASS_URL to your own Overpass instance (public servers are not used)")
    return url


def fetch_osm_buildings(bbox: list[float], out_path: Path) -> list[dict]:
    """OSM building ways in the box as GeoJSON features (tags in properties), cached in out_path."""
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8")).get("features") or []
    w, s, e, n = bbox
    query = f'[out:json][timeout:90];(way["building"]({s},{w},{n},{e}););out body;>;out skel qt;'
    req = urllib.request.Request(overpass_endpoint(), data=urllib.parse.urlencode({"data": query}).encode(),
                                 headers={"User-Agent": "geo-video-factory-plateau-pp/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    nodes = {el["id"]: (float(el["lon"]), float(el["lat"])) for el in raw.get("elements", []) if el.get("type") == "node"}
    features = []
    for el in raw.get("elements", []):
        tags = el.get("tags") or {}
        if el.get("type") != "way" or tags.get("building") in ("no", None):
            continue
        coords = [list(nodes[i]) for i in el.get("nodes", []) if i in nodes]
        if len(coords) < 4:
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        features.append({"type": "Feature", "id": f"way/{el['id']}", "properties": {**tags, "@id": f"way/{el['id']}"},
                         "geometry": {"type": "Polygon", "coordinates": [coords]}})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
                        encoding="utf-8")
    return features


def roof_texture_entry(image: str, bounds: list[float], center: list[float]) -> dict:
    """Photo bounds in the renderer's local metres around the manifest centre."""
    kx, ky = 111_320.0 * math.cos(math.radians(center[1])), 110_950.0
    w, s, e, n = bounds
    return {"image": image, "bounds": bounds,
            "bounds_m": [(w - center[0]) * kx, (s - center[1]) * ky, (e - center[0]) * kx, (n - center[1]) * ky]}


def cache_dirs(out: Path, cache: Path | None = None, gsi_cache: Path | None = None) -> tuple[Path, Path]:
    """(files that belong to this box, GSI tiles). The box's OSM extract sits beside the output in <out>-cache; GSI tiles, the same for every box, go to the shared cache (shared_cache.gsi_dir)."""
    from shared_cache import gsi_dir
    out = Path(out)
    return (Path(cache) if cache else out.parent / (out.name + "-cache"),
            Path(gsi_cache) if gsi_cache else gsi_dir())


CONTEXT_M = 300.0   # what is read around the box, so a building near its edge is judged as in a box around it


def grow(bbox: list[float], metres: float) -> list[float]:
    """The box widened by metres on every side."""
    import math
    w, s, e, n = bbox
    dlat = metres / 110_950.0
    dlon = metres / (111_320.0 * math.cos(math.radians((s + n) / 2)))
    return [round(w - dlon, 7), round(s - dlat, 7), round(e + dlon, 7), round(n + dlat, 7)]


def cell_models(footprints: list[dict], tileset: str, gsi: Path):
    """(lon, lat) -> height model of the JIS mesh cell there, calibrated on the PLATEAU buildings and GSI footprints
    of the whole cells the footprints lie in (cell_heights), so a building's height does not depend on the box."""
    from buildings import cell_heights
    from buildings.gsi_footprints import fetch_gsi_buildings
    cells = cell_heights.cells_of(footprints)
    if not cells:
        return cell_heights.model_for({})
    box = cell_heights.cells_box(cells)
    try:
        heights = cell_heights.feature_heights(tileset, box)
    except ValueError as error:                      # no PLATEAU here: the prior heights
        if "no leaf content" not in str(error):
            raise
        heights = {}
    return cell_heights.model_for(cell_heights.cell_height_models(cells, heights, fetch_gsi_buildings(box, gsi)))


def build(out: Path, bbox: list[float], tileset: str = TOKYO_2025, cache: Path | None = None,
          seed: str = "plateau-pp", gsi_cache: Path | None = None, bake: bool = True) -> dict:
    """The box's manifest and links into the per-tile store (pp_tiles), making only the tiles no box made before."""
    from buildings import pp_tiles
    if not bake:
        raise SystemExit("--no-bake was dropped in PLATEAU++ 0.3.0: tiles are kept baked, once, for every box")
    _, gsi = cache_dirs(Path(out), cache, gsi_cache)
    m = pp_tiles.assemble(Path(out), list(bbox), tileset, gsi, seed)
    print(f"PLATEAU++: {m['tile_count']} tiles, {m['plateau_building_count']} PLATEAU buildings, "
          f"{m['city_proxy_building_count']} filled-in, {len(m['removed_buildings'])} removed as implausible", flush=True)
    return m


def cache_key(bbox: list[float], tileset: str = TOKYO_2025, seed: str = "plateau-pp") -> str:
    """What decides a build besides the version: tileset, box (to 1e-6 degrees, about 0.1 m) and seed."""
    import hashlib
    request = {"tileset": tileset, "bbox": [round(float(v), 6) for v in bbox], "seed": seed,
               "texture": [2048, 1024]}
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:16]


def cache_dir(bbox: list[float], tileset: str = TOKYO_2025, seed: str = "plateau-pp") -> Path:
    """A box's directory: its manifest and links into the per-tile store (pp_tiles.store()), nothing heavier."""
    from buildings import pp_tiles
    return pp_tiles.store() / "boxes" / cache_key(bbox, tileset, seed)


def cached(bbox: list[float], tileset: str = TOKYO_2025, seed: str = "plateau-pp") -> Path:
    """The PLATEAU++ of this box: its manifest and links into the per-tile store, written once per version.

    The links are written into <dir>.<pid>.part and moved into place when done, so a box stopped half way is never
    read. A box comes out the same whoever builds it (the tiles are idempotent, pp_tiles), so two runs asking for one
    box need no lock: each builds its own .part, the first to finish moves it into place, and the other drops its own.
    A .part left by a run that stopped holds links only and is ignored. request.json says what the directory holds.
    The tiles themselves are kept once for every box (pp_tiles), so another box costs only the tiles it adds.
    """
    import shutil
    final = cache_dir(bbox, tileset, seed)
    if (final / "manifest.json").exists():
        return final
    final.parent.mkdir(parents=True, exist_ok=True)
    part = final.with_name(f"{final.name}.{os.getpid()}.part")
    part.mkdir(parents=True, exist_ok=True)   # a dead run's with our pid: building over it gives the same box
    build(part, list(bbox), tileset, None, seed, None, True)
    (part / "request.json").write_text(json.dumps({"version": PLATEAU_PP_VERSION, "tileset": tileset,
                                                   "bbox": list(bbox), "seed": seed}, indent=1) + "\n", encoding="utf-8")
    try:
        part.rename(final)
    except OSError:
        if not (final / "manifest.json").exists():
            raise
    if part.exists():                     # another run finished the same box first: take its, drop ours
        shutil.rmtree(part, ignore_errors=True)
    return final


def main(argv: list[str]) -> None:
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in argv if a.startswith("--"))
    bbox = [float(v) for v in opts["bbox"].split(",")]
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:                                      # no output named: the versioned shared cache
        print(cached(bbox, opts.get("tileset", TOKYO_2025), opts.get("seed", "plateau-pp")))
        return
    out = Path(paths[0]).resolve()
    build(out, bbox, opts.get("tileset", TOKYO_2025),
          Path(opts["cache"]).resolve() if "cache" in opts else None, opts.get("seed", "plateau-pp"),
          Path(opts["gsi-cache"]).resolve() if "gsi-cache" in opts else None, bake="no-bake" not in opts)


if __name__ == "__main__":
    main(sys.argv[1:])
