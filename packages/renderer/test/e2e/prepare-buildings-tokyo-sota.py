#!/usr/bin/env python3
"""Prepare assets for buildings-tokyo-sota.

baseline: PLATEAU 3D Tiles only (Hamura has none; Fussa has untextured LOD2).
sota:     PLATEAU + every GSI building footprint PLATEAU lacks, set on the GSI DEM, with heights
          calibrated on the PLATEAU buildings, pitched roofs, orthophoto roof colors (city_proxy).

Needs packages/pipeline/requirements-dev.txt (DracoPy, shapely). Set OVERPASS_URL to your own
Overpass instance for the OSM tags (height, levels).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image

TILESET_URL = "https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13-bldg-lod2-texture-2025/tileset.json"
BBOX = [139.302, 35.736, 139.336, 35.768]  # Tokyo Hamura (0% PLATEAU -> 100% OSM) <-> Tokyo Fussa (untextured PLATEAU)
# Opening: the 3D Tokyo everyone expects (West Shinjuku high-rises, textured PLATEAU).
SHINJUKU_BBOX = [139.674, 35.683, 139.702, 35.700]
SEED = "tokyo-sota-v1"
SOTA_VERSION = 9  # bump when the SOTA assets change shape, so cached ones are rebuilt
FIXTURES = ("buildings-tokyo-sota.json",)
# Set OVERPASS_URL to your own Overpass instance; the public ones are shared resources.
OVERPASS_ENDPOINTS = [os.environ["OVERPASS_URL"]] if os.environ.get("OVERPASS_URL") else [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def cache_is_complete(manifest_path: Path, *, require_sota: bool = False) -> bool:
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if require_sota and manifest.get("sota_prepared") != SOTA_VERSION:
        return False
    tiles = manifest.get("tiles") or []
    return bool(tiles) and all((manifest_path.parent / tile["glb"]).is_file() for tile in tiles)


def fetch_osm_buildings(bbox: list[float], out_path: Path) -> list[dict]:
    if out_path.exists():
        data = json.loads(out_path.read_text(encoding="utf-8"))
        return data.get("features") or []

    w, s, e, n = bbox
    query = (
        f"[out:json][timeout:90];"
        f"("
        f'  way["building"]({s},{w},{n},{e});'
        f");"
        f"out body;>;out skel qt;"
    )
    payload = urllib.parse.urlencode({"data": query}).encode("utf-8")
    raw = None
    last_err: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={"User-Agent": "geo-video-factory-e2e/1.0"},
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = json.loads(resp.read().decode("utf-8"))
                break
            except Exception as exc:
                last_err = exc
                time.sleep(1.0)
        if raw is not None:
            break
    if raw is None:
        raise RuntimeError(f"Overpass API failed: {last_err}")

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

    out_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    return features


def prepare_orthophoto(bbox: list[float], out_path: Path, bounds_path: Path) -> tuple[Image.Image, list[float]]:
    if out_path.exists() and bounds_path.exists():
        return Image.open(out_path).convert("RGB"), json.loads(bounds_path.read_text(encoding="utf-8"))
    from geo.seasonal_ortho import fetch_gsi_ortho_mosaic

    mosaic, bounds = fetch_gsi_ortho_mosaic(tuple(bbox), zoom=16)
    img = Image.fromarray(mosaic).convert("RGB")
    img.save(out_path)
    bounds_path.write_text(json.dumps(bounds), encoding="utf-8")
    return img, bounds


def crop_orthophoto(img: Image.Image, img_bounds: list[float], target_bbox: list[float]) -> Image.Image:
    bw, bs, be, bn = img_bounds
    w, s, e, n = target_bbox
    x0 = max(0, int(round((w - bw) / (be - bw) * img.width)))
    x1 = min(img.width, int(round((e - bw) / (be - bw) * img.width)))
    y0 = max(0, int(round((bn - n) / (bn - bs) * img.height)))
    y1 = min(img.height, int(round((bn - s) / (bn - bs) * img.height)))
    return img.crop((x0, y0, x1, y1))


def roof_texture_entry(image: str, bounds: list[float], center: list[float]) -> dict:
    """Photo bounds in the renderer's local meters around the manifest center."""
    kx = 111_320.0 * math.cos(math.radians(center[1]))
    ky = 110_950.0
    w, s, e, n = bounds
    return {"image": image, "bounds": bounds,
            "bounds_m": [(w - center[0]) * kx, (s - center[1]) * ky, (e - center[0]) * kx, (n - center[1]) * ky]}


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: prepare-buildings-tokyo-sota.py WORK_PROJECT [FIXTURE...]")

    renderer_dir = Path(__file__).resolve().parents[2]
    repository_dir = renderer_dir.parents[1]
    project_dir = Path(sys.argv[1]).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    for fixture_name in FIXTURES:
        fixture = renderer_dir / "test/fixtures" / fixture_name
        shutil.copy2(fixture, project_dir / fixture.name)

    assets_root = project_dir / "assets/buildings-tokyo-sota"
    baseline_dir = assets_root / "baseline"
    sota_dir = assets_root / "sota"
    baseline_manifest_path = baseline_dir / "manifest.json"
    sota_manifest_path = sota_dir / "manifest.json"

    sys.path.insert(0, str(repository_dir / "packages/pipeline"))
    from buildings.plateau_3d import prepare_tiles
    from buildings.building_appearance import apply_orthophoto_palette
    from buildings.building_heights import calibrate_height_model, footprint_area_m2
    from buildings.city_proxy import build_city_proxy_tile, wall_hex
    from buildings.glb_spatial import extract_glb_feature_heights
    from buildings.gsi_footprints import dem_sampler, fetch_gsi_buildings, orthophoto_texture

    if not cache_is_complete(baseline_manifest_path):
        manifest = prepare_tiles(
            TILESET_URL,
            BBOX,
            baseline_dir,
            max_texture_dimension=2048,
            far_texture_dimension=1024,
            workers=3,
        )
        if not manifest.get("tiles"):
            raise RuntimeError("PLATEAU preparation produced no building tiles")
        print(f"prepared {manifest['tile_count']} baseline PLATEAU tiles in {baseline_dir}")
    else:
        print(f"using cached baseline PLATEAU models: {baseline_manifest_path}")

    prelude_dir = assets_root / "shinjuku"
    if not cache_is_complete(prelude_dir / "manifest.json"):
        manifest = prepare_tiles(
            TILESET_URL,
            SHINJUKU_BBOX,
            prelude_dir,
            max_texture_dimension=2048,
            far_texture_dimension=1024,
            workers=3,
        )
        print(f"prepared {manifest['tile_count']} Shinjuku PLATEAU tiles ({manifest['tile_ids']} buildings)")
    else:
        print(f"using cached Shinjuku PLATEAU models: {prelude_dir}")

    # Enhanced Shinjuku: same PLATEAU models, a facade palette for the untextured ones and the
    # aerial photo for their roofs (the renderer adds the facade pattern).
    prelude_sota_dir = assets_root / "shinjuku-sota"
    if not cache_is_complete(prelude_sota_dir / "manifest.json", require_sota=True):
        if prelude_sota_dir.exists():
            shutil.rmtree(prelude_sota_dir)
        shutil.copytree(prelude_dir, prelude_sota_dir)
        shinjuku = json.loads((prelude_sota_dir / "manifest.json").read_text(encoding="utf-8"))
        heights = {}
        for tile in shinjuku["tiles"]:
            heights.update(extract_glb_feature_heights((prelude_sota_dir / tile["glb"]).read_bytes(), tile["rtc"], tile["ids"]))
            tile["facade_colors"] = [wall_hex(str(i), heights.get(str(i), {}).get("height", 20.0)) for i in tile["ids"]]
        photo, photo_bounds = orthophoto_texture(SHINJUKU_BBOX, assets_root / "gsi-cache", zoom=18)
        photo.save(prelude_sota_dir / "roof-photo.jpg", quality=90)
        shinjuku["roof_texture"] = roof_texture_entry("roof-photo.jpg", photo_bounds, shinjuku["center"])
        shinjuku["sota_prepared"] = SOTA_VERSION
        (prelude_sota_dir / "manifest.json").write_text(json.dumps(shinjuku, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"prepared enhanced Shinjuku manifest ({len(heights)} buildings)")

    if not cache_is_complete(sota_manifest_path, require_sota=True):
        if sota_dir.exists():
            shutil.rmtree(sota_dir)
        shutil.copytree(baseline_dir, sota_dir)
        baseline_manifest = json.loads(baseline_manifest_path.read_text(encoding="utf-8"))
        ortho_bbox = list(BBOX)
        for tile in baseline_manifest.get("tiles", []):
            reg = tile.get("region")
            if isinstance(reg, list) and len(reg) >= 4:
                ortho_bbox[0] = min(ortho_bbox[0], math.degrees(reg[0]))
                ortho_bbox[1] = min(ortho_bbox[1], math.degrees(reg[1]))
                ortho_bbox[2] = max(ortho_bbox[2], math.degrees(reg[2]))
                ortho_bbox[3] = max(ortho_bbox[3], math.degrees(reg[3]))
        ortho_path = assets_root / "ortho.png"
        ortho_bounds_path = assets_root / "ortho_bounds.json"
        ortho_full, ortho_bounds = prepare_orthophoto(ortho_bbox, ortho_path, ortho_bounds_path)
        manifest = apply_orthophoto_palette(sota_dir, ortho_path, bbox_degrees=ortho_bounds, seed=SEED)

        # Complete footprints (GSI) and the ground they stand on (GSI DEM, as draped by the renderer).
        gsi_cache = assets_root / "gsi-cache"
        footprints = fetch_gsi_buildings(BBOX, gsi_cache)
        ground = dem_sampler(BBOX, gsi_cache)

        # PLATEAU buildings: exclude the footprints they model, and calibrate heights on them.
        from shapely.geometry import Point, shape
        from shapely.strtree import STRtree
        plateau = {}
        for tile in manifest.get("tiles", []):
            plateau.update(extract_glb_feature_heights((sota_dir / tile["glb"]).read_bytes(), tile["rtc"], tile["ids"]))
        if manifest.get("tiles") and not plateau:
            raise RuntimeError("no PLATEAU building heights could be read (is DracoPy installed?)")
        polygons = [shape(f["geometry"]) for f in footprints]
        tree = STRtree(polygons)
        samples = []
        casters = {}
        for item in plateau.values():
            hits = tree.query(Point(*item["lonlat"]), predicate="within")
            if len(hits):
                f = footprints[int(hits[0])]
                samples.append((f["properties"]["vt_code"], footprint_area_m2(f["geometry"]["coordinates"][0]), item["height"]))
                casters[int(hits[0])] = max(casters.get(int(hits[0]), 0.0), item["height"])
        # Untextured PLATEAU walls get the same facade palette as the proxies, so the city reads as one.
        for tile in manifest.get("tiles", []):
            tile["facade_colors"] = [
                wall_hex(str(i), plateau.get(str(i), {}).get("height", 6.0)) for i in tile.get("ids", [])
            ]
        sota_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        model = calibrate_height_model(samples)
        print(f"GSI footprints: {len(footprints)}; PLATEAU buildings: {len(plateau)}; calibration samples: {len(samples)}")

        osm_features = fetch_osm_buildings(BBOX, assets_root / "osm-buildings.geojson")
        roof_photo, roof_bounds = orthophoto_texture(BBOX, gsi_cache, zoom=18)
        roof_photo.save(sota_dir / "roof-photo.jpg", quality=90)
        manifest = build_city_proxy_tile(
            footprints,
            BBOX,
            sota_dir,
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
        manifest["sota_prepared"] = SOTA_VERSION
        manifest["plateau_building_count"] = len(plateau)
        manifest["roof_texture"] = roof_texture_entry("roof-photo.jpg", roof_bounds, manifest["center"])
        sota_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"prepared SOTA manifest in {sota_dir}: {manifest['tile_count']} tiles, "
            f"{manifest['city_proxy_building_count']} city-proxy buildings"
        )
    else:
        print(f"using cached SOTA models: {sota_manifest_path}")

    # Counts shown on screen come from the prepared data, not from numbers typed into the fixture.
    sota_manifest = json.loads(sota_manifest_path.read_text(encoding="utf-8"))
    built = sota_manifest["city_proxy_building_count"]
    plateau_count = sota_manifest["plateau_building_count"]
    counts = {
        # quoted placeholders become JSON numbers (counters count up to them), bare ones text
        '"{{city_proxy_count}}"': str(built),
        '"{{total_count}}"': str(built + plateau_count),
        "{{city_proxy_count}}": f"{built:,}",
        "{{plateau_count}}": f"{plateau_count:,}",
        "{{total_count}}": f"{built + plateau_count:,}",
    }
    for fixture_name in FIXTURES:
        target = project_dir / fixture_name
        text = target.read_text(encoding="utf-8")
        for key, value in counts.items():
            text = text.replace(key, value)
        target.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
