#!/usr/bin/env python3
"""Prepare PLATEAU 3D buildings + city_proxy fallback buildings + pseudo-textures for Shibuya and Ginza close-up shots."""

from __future__ import annotations

import json
import math
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

PROJECT_DIR = Path(__file__).resolve().parents[2]
FLYOVER_DIR = PROJECT_DIR / "flyover"
REPO_ROOT = Path(__file__).resolve().parents[7]
sys.path.insert(0, str(REPO_ROOT / "packages/pipeline"))

from buildings.building_appearance import apply_orthophoto_palette
from buildings.building_heights import calibrate_height_model, footprint_area_m2
from buildings.city_proxy import build_city_proxy_tile, wall_hex
from buildings.glb_spatial import extract_glb_feature_heights
from buildings.gsi_footprints import dem_sampler, fetch_gsi_buildings, orthophoto_texture
from buildings.plateau_3d import prepare_tiles

TILESET_URL = "https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13-bldg-lod2-texture-2025/tileset.json"
OVERPASS_URL = "https://overpass.yuiseki.net/api/interpreter"
SEED = 42

AREAS = {
    "shibuya": [139.692, 35.652, 139.710, 35.667],
    "ginza": [139.756, 35.660, 139.778, 35.678],
    "nihonbashi": [139.766, 35.676, 139.792, 35.696],
    "asakusa": [139.782, 35.698, 139.812, 35.726],
}


def fetch_osm_buildings(bbox: list[float], out_path: Path) -> list[dict]:
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8")).get("features", [])
    w, s, e, n = bbox
    query = f"[out:json][timeout:60];(way[\"building\"]({s},{w},{n},{e}););out body;>;out skel qt;"
    req = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
        headers={"User-Agent": "geo-video-factory/tokyo-river-recall"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    nodes: dict[int, tuple[float, float]] = {}
    for el in raw.get("elements", []):
        if el.get("type") == "node":
            nodes[el["id"]] = (float(el["lon"]), float(el["lat"]))
    features: list[dict] = []
    for el in raw.get("elements", []):
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        if tags.get("building") in ("no", None):
            continue
        coords = [list(nodes[nid]) for nid in el.get("nodes", []) if nid in nodes]
        if len(coords) < 4:
            continue
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        if max(xs) - min(xs) < 1e-7 or max(ys) - min(ys) < 1e-7:
            continue
        features.append({
            "type": "Feature",
            "id": f"way/{el['id']}",
            "properties": {**tags, "@id": f"way/{el['id']}"},
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })
    out_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
    return features


def roof_texture_entry(image: str, bounds: list[float], center: list[float]) -> dict:
    kx = 111_320.0 * math.cos(math.radians(center[1]))
    ky = 110_950.0
    w, s, e, n = bounds
    return {
        "image": image,
        "bounds": bounds,
        "bounds_m": [(w - center[0]) * kx, (s - center[1]) * ky, (e - center[0]) * kx, (n - center[1]) * ky],
    }


def prepare_area(name: str, bbox: list[float]) -> None:
    area_dir = FLYOVER_DIR / "assets" / "buildings-3d" / name
    manifest_path = area_dir / "manifest.json"
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        if m.get("sota_prepared") and all((area_dir / t["glb"]).is_file() for t in m.get("tiles", [])):
            print(f"[{name}] using cached 3D buildings: {manifest_path}")
            return

    cache_dir = FLYOVER_DIR / "assets" / "buildings-3d" / "_cache" / name
    cache_dir.mkdir(parents=True, exist_ok=True)

    if manifest_path.exists() and all((area_dir / t["glb"]).is_file() for t in json.loads(manifest_path.read_text(encoding="utf-8")).get("tiles", [])):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(f"[{name}] reusing {manifest.get('tile_count', 0)} downloaded PLATEAU tiles")
    else:
        if area_dir.exists():
            shutil.rmtree(area_dir)
        area_dir.mkdir(parents=True, exist_ok=True)
        print(f"[{name}] fetching PLATEAU tiles for {bbox}...")
        manifest = prepare_tiles(
            TILESET_URL,
            bbox,
            area_dir,
            max_texture_dimension=1024,
            far_texture_dimension=512,
            workers=3,
        )
        print(f"[{name}] fetched {manifest.get('tile_count', 0)} PLATEAU tiles")

    # Expand ortho_bbox to cover all tile regions so edge buildings are within the orthophoto
    ortho_bbox = list(bbox)
    for tile in manifest.get("tiles", []):
        reg = tile.get("region")
        if isinstance(reg, list) and len(reg) >= 4:
            ortho_bbox[0] = min(ortho_bbox[0], math.degrees(reg[0]))
            ortho_bbox[1] = min(ortho_bbox[1], math.degrees(reg[1]))
            ortho_bbox[2] = max(ortho_bbox[2], math.degrees(reg[2]))
            ortho_bbox[3] = max(ortho_bbox[3], math.degrees(reg[3]))

    # Apply orthophoto palette and pseudo-facade colors
    ortho_photo, ortho_bounds = orthophoto_texture(ortho_bbox, cache_dir / "ortho_full", zoom=16)
    ortho_path = cache_dir / "ortho.png"
    ortho_photo.save(ortho_path)
    manifest = apply_orthophoto_palette(area_dir, ortho_path, bbox_degrees=ortho_bounds, seed=SEED)

    roof_photo, roof_bounds = orthophoto_texture(bbox, cache_dir, zoom=18)
    roof_photo.save(area_dir / "roof-photo.jpg", quality=90)

    # Extract PLATEAU heights & centroids for calibration and deduplication
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    footprints = fetch_gsi_buildings(bbox, cache_dir)
    ground = dem_sampler(bbox, cache_dir)

    plateau: dict = {}
    for tile in manifest.get("tiles", []):
        plateau.update(extract_glb_feature_heights((area_dir / tile["glb"]).read_bytes(), tile["rtc"], tile["ids"]))
        tile["facade_colors"] = [
            wall_hex(str(i), plateau.get(str(i), {}).get("height", 15.0)) for i in tile.get("ids", [])
        ]

    polygons = [shape(f["geometry"]) for f in footprints]
    tree = STRtree(polygons)
    samples = []
    casters: dict[int, float] = {}
    for item in plateau.values():
        hits = tree.query(Point(*item["lonlat"]), predicate="within")
        if len(hits):
            idx = int(hits[0])
            f = footprints[idx]
            samples.append((f["properties"]["vt_code"], footprint_area_m2(f["geometry"]["coordinates"][0]), item["height"]))
            casters[idx] = max(casters.get(idx, 0.0), item["height"])

    model = calibrate_height_model(samples) if samples else None
    osm_features = fetch_osm_buildings(bbox, cache_dir / "osm-buildings.geojson")

    manifest = build_city_proxy_tile(
        footprints,
        bbox,
        area_dir,
        ground=ground,
        orthophoto=roof_photo,
        orthophoto_bounds=roof_bounds,
        plateau_centroids=[item["lonlat"] for item in plateau.values()],
        osm_features=osm_features,
        height_model=model,
        seed=SEED,
        shadow_casters=[(footprints[i], h) for i, h in sorted(casters.items())],
        roof_texture=("roof-photo.jpg", roof_bounds),
    )
    manifest["sota_prepared"] = True
    manifest["plateau_building_count"] = len(plateau)
    manifest["roof_texture"] = roof_texture_entry("roof-photo.jpg", roof_bounds, manifest["center"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[{name}] ready: {manifest['tile_count']} tiles, "
        f"PLATEAU={len(plateau)}, city_proxy={manifest.get('city_proxy_building_count', 0)}"
    )


def main() -> None:
    for name, bbox in AREAS.items():
        prepare_area(name, bbox)


if __name__ == "__main__":
    main()
