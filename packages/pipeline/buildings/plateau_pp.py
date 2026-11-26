"""PLATEAU++: PLATEAU's own buildings and textures, synthesized only where PLATEAU has none.

    OVERPASS_URL=<your Overpass> python -m buildings.plateau_pp <out dir> --bbox=w,s,e,n
        [--tileset=<PLATEAU 3D Tiles tileset.json>] [--cache=<dir>] [--gsi-cache=<dir>] [--seed=plateau-pp] [--no-bake]

PLATEAU tiles as served and GSI tiles are kept in the shared cache (shared_cache: $GEO_VIDEO_CACHE, or tmp/.cache
of this repository), so another box or project reuses them; the OSM extract of this box goes to --cache
(default <out dir>-cache).

1. PLATEAU's building tiles with their own textures (plateau_3d.prepare_tiles).
2. Buildings that cannot be real are taken out of PLATEAU (plausibility: needles, complexes extruded to
   their tower's height, giant slabs) and listed in the manifest as removed_buildings.
3. Buildings PLATEAU left untextured get a wall colour from their ID and height (city_proxy.wall_hex: tall
   curtain walls or low houses, the same palette as the filled-in buildings) and the GSI photo (z18, roof-photo.jpg)
   on their roofs; textured ones are left alone. The renderer applies both only to untextured materials.
4. Every GSI footprint PLATEAU does not model, including the ones step 2 freed, becomes a filled-in building:
   on the GSI DEM, OSM building:levels before height, otherwise a height calibrated on PLATEAU (city_proxy).
   Where PLATEAU has no tiles at all, every building is filled in.
5. The look is baked into every GLB (pp_bake): roof photo, wall colour, windows and tone, so any glTF renderer shows
   the same city. manifest.plateau_pp names the version. --no-bake stops before this step and leaves the look to
   the renderer's draw-time shaders, as before v0.1.0 (to compare the two).

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

from buildings import glb_spatial
from buildings.glb_strip import drop_features
from buildings.plausibility import implausible

TOKYO_2025 = "https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13-bldg-lod2-texture-2025/tileset.json"


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


def remove_implausible(plateau_dir: Path, manifest: dict, osm_features: list[dict]) -> dict:
    """Take the buildings plausibility refuses out of every PLATEAU tile, and list them in the manifest."""
    removed = manifest.setdefault("removed_buildings", [])
    done = {r["id"] for r in removed}
    for tile in manifest["tiles"]:
        if tile.get("kind") in ("city-proxy", "city-shadow") or tile.get("frame") == "enu":
            continue
        path = Path(plateau_dir) / tile["glb"]
        raw = path.read_bytes()
        ids = [str(i) for i in tile.get("ids", [])]
        shapes = glb_spatial.extract_glb_feature_shapes(raw, tile["rtc"], ids)
        traps = {fid: trap for fid, trap in implausible(shapes, osm_features).items() if fid not in done}
        if not traps:
            continue
        new = drop_features(raw, {ids.index(fid) for fid in traps})
        path.write_bytes(new)
        tile["bytes"] = len(new)
        for fid, trap in sorted(traps.items()):
            s = shapes[fid]
            removed.append({"id": fid, "trap": trap, "lonlat": [round(v, 6) for v in s["lonlat"]],
                            "height": round(s["height"], 1), "area": round(s["area"], 1)})
            done.add(fid)
    return manifest


def cache_dirs(out: Path, cache: Path | None = None, gsi_cache: Path | None = None) -> tuple[Path, Path]:
    """(files that belong to this box, GSI tiles). The box's OSM extract sits beside the output in <out>-cache; GSI tiles, the same for every box, go to the shared cache (shared_cache.gsi_dir)."""
    from shared_cache import gsi_dir
    out = Path(out)
    return (Path(cache) if cache else out.parent / (out.name + "-cache"),
            Path(gsi_cache) if gsi_cache else gsi_dir())


def bake_tiles(out: Path, m: dict, roof_photo, roof_bounds: list[float]) -> None:
    """Write the look into every tile (pp_bake): PLATEAU tiles and filled-in tiles; the shadow tile stays as it is."""
    import hashlib

    from buildings import pp_bake
    for tile in m["tiles"]:
        if tile.get("kind") == "city-shadow":
            continue
        path = out / tile["glb"]
        raw = path.read_bytes()
        ids = [str(i) for i in tile.get("ids", [])]
        if tile.get("kind") == "city-proxy":
            new = pp_bake.bake_proxy(raw, ids, roof_photo, (tile.get("roof_texture") or m["roof_texture"])["bounds_m"])
        elif tile.get("frame") != "enu":
            new = pp_bake.bake_untextured(raw, tile["rtc"], ids, tile.get("facade_colors") or [], roof_photo, roof_bounds)
        else:
            continue
        path.write_bytes(new)
        tile["bytes"], tile["sha256"] = len(new), hashlib.sha256(new).hexdigest()
    m["plateau_pp"] = {"version": pp_bake.BAKE_VERSION, "baked": True}


def build(out: Path, bbox: list[float], tileset: str = TOKYO_2025, cache: Path | None = None,
          seed: str = "plateau-pp", gsi_cache: Path | None = None, bake: bool = True) -> dict:
    from buildings.building_heights import calibrate_height_model, footprint_area_m2
    from buildings.city_proxy import build_city_proxy_tile, wall_hex
    from buildings.gsi_footprints import dem_sampler, fetch_gsi_buildings, orthophoto_texture
    from buildings.plateau_3d import prepare_tiles
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    out = Path(out)
    cache, gsi = cache_dirs(out, cache, gsi_cache)
    cache.mkdir(parents=True, exist_ok=True)
    if not (out / "manifest.json").exists():
        try:
            prepare_tiles(tileset, bbox, out, max_texture_dimension=2048, far_texture_dimension=1024, workers=3)
        except ValueError as error:                     # PLATEAU has no model here: build from footprints alone
            if "no leaf content" not in str(error):
                raise
            (out / "models").mkdir(parents=True, exist_ok=True)
            (out / "manifest.json").write_text(json.dumps({
                "format": "geo-video-factory.plateau-3d/1", "tileset_url": tileset, "bbox_degrees": bbox,
                "center": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2], "tile_count": 0, "tile_ids": 0,
                "tiles": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("no PLATEAU tiles in the box: filled-in buildings only", flush=True)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    osm = fetch_osm_buildings(bbox, cache / "osm-buildings.geojson")
    m = remove_implausible(out, m, osm)
    (out / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"removed {len(m['removed_buildings'])} implausible PLATEAU buildings", flush=True)


    footprints = fetch_gsi_buildings(bbox, gsi)
    ground = dem_sampler(bbox, gsi)
    plateau = {}
    for tile in m["tiles"]:
        plateau.update(glb_spatial.extract_glb_feature_heights((out / tile["glb"]).read_bytes(), tile["rtc"], tile["ids"]))
    tree = STRtree([shape(f["geometry"]) for f in footprints])
    samples, casters = [], {}
    for item in plateau.values():
        hits = tree.query(Point(*item["lonlat"]), predicate="within")
        if len(hits):
            f = footprints[int(hits[0])]
            samples.append((f["properties"]["vt_code"], footprint_area_m2(f["geometry"]["coordinates"][0]), item["height"]))
            casters[int(hits[0])] = max(casters.get(int(hits[0]), 0.0), item["height"])
    for tile in m["tiles"]:
        tile["facade_colors"] = [wall_hex(str(i), plateau.get(str(i), {}).get("height", 6.0)) for i in tile["ids"]]
    (out / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    roof, roof_bounds = orthophoto_texture(bbox, gsi, zoom=18)
    roof.save(out / "roof-photo.jpg", quality=90)
    removed = m.get("removed_buildings", [])
    m = build_city_proxy_tile(
        footprints, bbox, out, ground=ground, orthophoto=roof, orthophoto_bounds=roof_bounds,
        plateau_centroids=[item["lonlat"] for item in plateau.values()], osm_features=osm,
        height_model=calibrate_height_model(samples), seed=seed,
        shadow_casters=[(footprints[i], h) for i, h in sorted(casters.items())],
        roof_texture=("roof-photo.jpg", roof_bounds))
    m["removed_buildings"] = removed
    m["plateau_building_count"] = len(plateau)
    m["roof_texture"] = roof_texture_entry("roof-photo.jpg", roof_bounds, m["center"])
    if bake:
        bake_tiles(out, m, roof, roof_bounds)
    (out / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PLATEAU++: {m['tile_count']} tiles, {len(plateau)} PLATEAU buildings, "
          f"{m['city_proxy_building_count']} filled-in, {len(removed)} removed as implausible")
    return m


def main(argv: list[str]) -> None:
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in argv if a.startswith("--"))
    out = Path([a for a in argv if not a.startswith("--")][0]).resolve()
    build(out, [float(v) for v in opts["bbox"].split(",")], opts.get("tileset", TOKYO_2025),
          Path(opts["cache"]).resolve() if "cache" in opts else None, opts.get("seed", "plateau-pp"),
          Path(opts["gsi-cache"]).resolve() if "gsi-cache" in opts else None, bake="no-bake" not in opts)


if __name__ == "__main__":
    main(sys.argv[1:])
