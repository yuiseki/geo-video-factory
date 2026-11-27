"""PLATEAU++ kept once per tile and shared by every box: a box is only a list of the tiles it uses.

    <store>/plateau/<dd>/<digest>.glb (+ .json)      one PLATEAU tile, baked; <digest> names the served tile as the
                                                     shared plateau-raw cache does (sha256 of its URL, 20 digits)
    <store>/proxy/<seed>/16/<x>/<y>/ (meta.json)     the filled-in buildings and the ground shadow of the footprints
                                                     whose centre lies in GSI z16 tile x/y
    <box>/manifest.json, <box>/models/*              what a box uses: links into the store, nothing else

<store> is tmp/.cache/plateau-pp/v<PLATEAU_PP_VERSION> (shared_cache). A tile comes out the same in every box (each
step reads what stands around the tile, never the box: OSM and GSI within CONTEXT_M, heights per JIS mesh cell, the
roof photo of the tile's own region), so it is written once and never rewritten; a new box only adds the tiles no
box asked for before. Filled-in tiles are written as ECEF offsets from their own RTC centre (enu_rtc), like
PLATEAU's, so no box centre is involved.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

OSM_ZOOM = 15          # OSM is fetched and kept per z15 tile (about 1.2 km) and joined around each tile
PROXY_ZOOM = 16        # filled-in buildings are kept per GSI z16 tile, the zoom their footprints come at
_osm_lock = threading.Lock()   # tiles are made on several threads; one z15 OSM file is fetched once


def store() -> Path:
    from buildings.plateau_pp import PLATEAU_PP_VERSION
    from shared_cache import plateau_pp_dir
    return plateau_pp_dir(PLATEAU_PP_VERSION)


def digest(uri: str) -> str:
    """The name the shared plateau-raw cache gives the served tile (shared_cache.cached_fetch)."""
    return hashlib.sha256(uri.encode()).hexdigest()[:20]


def _write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + f".part{os.getpid()}")
    part.write_bytes(data)
    part.replace(path)


def osm_around(box: list[float]) -> list[dict[str, Any]]:
    """OSM buildings of every z15 tile the box touches, each tile fetched once (own Overpass) and kept."""
    from buildings.gsi_footprints import tile_bbox, tiles_for_bbox
    from buildings.plateau_pp import fetch_osm_buildings
    from shared_cache import cache_root
    seen: dict[str, dict[str, Any]] = {}
    for x, y in tiles_for_bbox(box, OSM_ZOOM):
        path = cache_root() / "osm" / "buildings" / str(OSM_ZOOM) / str(x) / f"{y}.geojson"
        with _osm_lock:
            found = fetch_osm_buildings(tile_bbox(OSM_ZOOM, x, y), path)
        for f in found:
            seen.setdefault(f["id"], f)
    return [seen[k] for k in sorted(seen)]


def _degrees(region: list[float]) -> list[float]:
    return [math.degrees(v) for v in region[:4]]


def plateau_tile(item: dict[str, Any], gsi: Path, fetch) -> dict[str, Any]:
    """The baked PLATEAU tile of one leaf (iter_leaf_contents item), made once: textures at 2048, the buildings
    plausibility refuses taken out (OSM around the tile), walls coloured by ID and height, roofs from the photo of
    the tile's region. Returns its manifest entry; glb is relative to the store."""
    meta_path = store() / "plateau" / digest(item["uri"])[:2] / f"{digest(item['uri'])}.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    from buildings import glb_spatial, pp_bake
    from buildings.city_proxy import wall_hex
    from buildings.glb_strip import drop_features
    from buildings.gsi_footprints import orthophoto_texture
    from buildings.plateau_3d import _parse_tile, _resize_glb_textures
    from buildings.plateau_pp import CONTEXT_M, grow
    from buildings.plausibility import implausible
    glb, ids, rtc, document = _parse_tile(fetch(item["uri"]), item["uri"])
    rtc = [float(v) for v in rtc]
    ids = [str(i) for i in ids]
    glb = _resize_glb_textures(glb, 2048)
    centroids = glb_spatial.extract_glb_feature_centroids(glb, rtc, ids) if ids else {}
    region = item.get("region")
    if region is None and centroids:          # a leaf without a bounding region: the extent of its buildings
        lons, lats = [c[0] for c in centroids.values()], [c[1] for c in centroids.values()]
        box = [min(lons), min(lats), max(lons), max(lats)]
    else:
        box = _degrees(region) if region else None
    removed = []
    if ids and box:
        shapes = glb_spatial.extract_glb_feature_shapes(glb, rtc, ids)
        traps = implausible(shapes, osm_around(grow(box, CONTEXT_M)))
        if traps:
            glb = drop_features(glb, {ids.index(fid) for fid in traps})
            for fid, trap in sorted(traps.items()):
                s = shapes[fid]
                removed.append({"id": fid, "trap": trap, "lonlat": [round(v, 6) for v in s["lonlat"]],
                                "height": round(s["height"], 1), "area": round(s["area"], 1)})
    heights = glb_spatial.extract_glb_feature_heights(glb, rtc, ids) if ids else {}
    colours = [wall_hex(i, heights.get(i, {}).get("height", 6.0)) for i in ids]
    if box:
        photo, bounds = orthophoto_texture(box, gsi, zoom=18)
        glb = pp_bake.bake_untextured(glb, rtc, ids, colours, photo, bounds)
    rel = f"plateau/{digest(item['uri'])[:2]}/{digest(item['uri'])}.glb"
    entry = {"source": item["uri"], "glb": rel, "rtc": rtc, "ids": ids, "region": region, "depth": item.get("depth"),
             "texture_limit": 2048, "facade_colors": colours, "feature_centroids": centroids,
             "heights": {i: [round(h["lonlat"][0], 7), round(h["lonlat"][1], 7), round(h["height"], 2)]
                         for i, h in sorted(heights.items())},
             "removed_buildings": removed, "bytes": len(glb), "sha256": hashlib.sha256(glb).hexdigest(),
             "extensions": document.get("extensionsUsed", [])}
    _write_once(store() / rel, glb)
    _write_once(meta_path, (json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n").encode())
    return entry


def _tile_of(feature: dict[str, Any], z: int) -> tuple[int, int]:
    from buildings.gsi_footprints import _fractional_tile
    ring = feature["geometry"]["coordinates"][0][:-1] or feature["geometry"]["coordinates"][0]
    lon, lat = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
    fx, fy = _fractional_tile(lon, lat, z)
    return math.floor(fx), math.floor(fy)


def proxy_tile(x: int, y: int, tileset: str, gsi: Path, seed: str, fetch) -> list[dict[str, Any]]:
    """The filled-in buildings and ground shadow of the GSI footprints whose centre lies in z16 tile x/y, made once.
    Returns their manifest entries (paths relative to the store)."""
    folder = store() / "proxy" / seed / str(PROXY_ZOOM) / str(x) / str(y)
    if (folder / "meta.json").exists():
        return json.loads((folder / "meta.json").read_text(encoding="utf-8"))["tiles"]
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
    from buildings import pp_bake
    from buildings.city_proxy import build_city_proxy_tile
    from buildings.enu_rtc import to_rtc
    from buildings.gsi_footprints import dem_sampler, fetch_gsi_buildings, orthophoto_texture, tile_bbox
    from buildings.plateau_3d import _leaf_items
    from buildings.plateau_mesh import GEOID_M
    from buildings.plateau_pp import CONTEXT_M, cell_models, grow
    box = tile_bbox(PROXY_ZOOM, x, y)
    context = grow(box, CONTEXT_M)
    around = fetch_gsi_buildings(context, gsi)
    mine = [f for f in around if _tile_of(f, PROXY_ZOOM) == (x, y)]
    entries: list[dict[str, Any]] = []
    if mine:
        plateau = {}
        for item in _leaf_items(tileset, context, fetch):
            for i, (lon, lat, h) in plateau_tile(item, gsi, fetch)["heights"].items():
                plateau[i] = {"lonlat": [lon, lat], "height": h}
        tree = STRtree([shape(f["geometry"]) for f in mine])
        casters: dict[int, float] = {}
        for key in sorted(plateau):
            hits = tree.query(Point(*plateau[key]["lonlat"]), predicate="within")
            if len(hits):
                k = int(min(hits))
                casters[k] = max(casters.get(k, 0.0), plateau[key]["height"])
        roof, roof_bounds = orthophoto_texture(context, gsi, zoom=18)
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            m = build_city_proxy_tile(
                mine, box, work, ground=dem_sampler(context, gsi), orthophoto=roof, orthophoto_bounds=roof_bounds,
                plateau_centroids=[p["lonlat"] for p in plateau.values()], osm_features=osm_around(context),
                height_model=cell_models(mine, tileset, gsi), seed=seed,
                shadow_casters=[(mine[i], h) for i, h in sorted(casters.items())],
                roof_texture=("roof-photo.jpg", roof_bounds))
            lon0, lat0 = m["center"]
            for tile in m["tiles"]:
                raw = (work / tile["glb"]).read_bytes()
                if tile.get("kind") == "city-proxy":
                    raw = pp_bake.bake_proxy(raw, [str(i) for i in tile.get("ids", [])], roof,
                                             (tile.get("roof_texture") or m["roof_texture"])["bounds_m"])
                glb, rtc = to_rtc(raw, lon0, lat0, GEOID_M)
                name = Path(tile["glb"]).name
                _write_once(folder / name, glb)
                entry = {"kind": tile.get("kind"), "glb": f"{folder.relative_to(store()).as_posix()}/{name}",
                         "rtc": rtc, "ids": tile.get("ids", []), "bytes": len(glb),
                         "sha256": hashlib.sha256(glb).hexdigest()}
                if tile.get("buildings"):
                    side = Path(tile["buildings"]).name
                    shutil.copyfile(work / tile["buildings"], folder / side)
                    entry["buildings"] = f"{folder.relative_to(store()).as_posix()}/{side}"
                entries.append(entry)
    _write_once(folder / "meta.json", (json.dumps({"tiles": entries}, ensure_ascii=False) + "\n").encode())
    return entries


def assemble(out: Path, bbox: list[float], tileset: str, gsi: Path, seed: str = "plateau-pp",
             workers: int = 3) -> dict[str, Any]:
    """Write <out>/manifest.json and <out>/models/ (relative links into the store) for the box, making only the
    tiles no box made before."""
    from concurrent.futures import ThreadPoolExecutor
    from buildings.gsi_footprints import tiles_for_bbox
    from buildings.plateau_3d import _cached_fetcher, _leaf_items
    from buildings.plateau_pp import PLATEAU_PP_VERSION
    fetch = _cached_fetcher(None, None)
    leaves = _leaf_items(tileset, bbox, fetch)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        plateau = list(pool.map(lambda item: plateau_tile(item, gsi, fetch), leaves))
    proxies = [e for x, y in tiles_for_bbox(bbox, PROXY_ZOOM) for e in proxy_tile(x, y, tileset, gsi, seed, fetch)]
    out = Path(out)
    models = out / "models"
    if models.exists():
        shutil.rmtree(models)            # links only: the store is never touched
    models.mkdir(parents=True)
    tiles = []
    for entry in plateau + proxies:
        tile = {k: v for k, v in entry.items() if k != "heights"}
        for key in ("glb", "buildings"):
            if key in tile:
                target = store() / tile[key]
                link = models / tile[key].replace("/", "_")
                link.symlink_to(os.path.relpath(target, models))
                tile[key] = f"models/{link.name}"
        tiles.append(tile)
    removed = [r for e in plateau for r in e.get("removed_buildings", [])]
    m = {"format": "geo-video-factory.plateau-3d/1", "tileset_url": tileset, "bbox_degrees": bbox,
         "center": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2], "tile_count": len(tiles),
         "tile_ids": len({i for t in tiles for i in t.get("ids", [])}), "texture_max_dimension": 2048,
         "tiles": tiles, "removed_buildings": removed,
         "plateau_building_count": sum(len(e.get("heights", {})) for e in plateau),
         "city_proxy_building_count": sum(len(e.get("ids", [])) for e in proxies if e.get("kind") == "city-proxy"),
         "plateau_pp": {"version": PLATEAU_PP_VERSION, "baked": True, "store": "per tile"}}
    (out / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return m
