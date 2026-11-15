#!/usr/bin/env python3
"""Prepare baseline (raw PLATEAU) and SOTA (PLATEAU + GSI ortho + OSM proxy) assets for buildings-tokyo-sota."""
from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image

TILESET_URL = "https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13-bldg-lod2-texture-2025/tileset.json"
BBOX = [139.302, 35.736, 139.336, 35.768]  # Tokyo Hamura (0% PLATEAU -> 100% OSM) <-> Tokyo Fussa (untextured PLATEAU)
SEED = "tokyo-sota-v1"
OVERPASS_ENDPOINTS = [
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
    if require_sota and not manifest.get("sota_prepared"):
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
    from seasonal_ortho import fetch_gsi_ortho_mosaic

    mosaic, bounds = fetch_gsi_ortho_mosaic(tuple(bbox), zoom=16)
    img = Image.fromarray(mosaic, mode="RGB")
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


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: prepare-buildings-tokyo-sota.py WORK_PROJECT [FIXTURE...]")

    renderer_dir = Path(__file__).resolve().parents[2]
    repository_dir = renderer_dir.parents[1]
    project_dir = Path(sys.argv[1]).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    for fixture_name in (
        "buildings-tokyo-sota-baseline.json",
        "buildings-tokyo-sota-enhanced.json",
    ):
        fixture = renderer_dir / "test/fixtures" / fixture_name
        shutil.copy2(fixture, project_dir / fixture.name)

    assets_root = project_dir / "assets/buildings-tokyo-sota"
    baseline_dir = assets_root / "baseline"
    sota_dir = assets_root / "sota"
    baseline_manifest_path = baseline_dir / "manifest.json"
    sota_manifest_path = sota_dir / "manifest.json"

    sys.path.insert(0, str(repository_dir / "packages/pipeline"))
    from plateau_3d import prepare_tiles
    from building_appearance import apply_orthophoto_palette, sample_polygon_color
    from osm_proxy import build_osm_proxy_tiles, _height

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
        ortho_cropped = crop_orthophoto(ortho_full, ortho_bounds, BBOX)

        osm_path = assets_root / "osm-buildings.geojson"
        raw_features = fetch_osm_buildings(BBOX, osm_path)
        valid_features = []
        fallback_count = 0
        for feat in raw_features:
            props = dict(feat.get("properties") or {})
            try:
                _height(props)
            except ValueError:
                props["building:levels"] = "1"
                fallback_count += 1
            feat = {**feat, "properties": props}
            try:
                ring = feat["geometry"]["coordinates"][0]
                sample_polygon_color(ortho_cropped, ring, BBOX)
                valid_features.append(feat)
            except ValueError:
                continue
        print(f"OSM valid features: {len(valid_features)} (1-story fallback: {fallback_count})")

        plateau_ids = {
            str(identifier)
            for tile in manifest.get("tiles", [])
            for identifier in tile.get("ids", [])
        }
        manifest = build_osm_proxy_tiles(
            valid_features,
            BBOX,
            sota_dir,
            plateau_ids=plateau_ids,
            seed=SEED,
            orthophoto=ortho_cropped,
        )
        manifest["sota_prepared"] = True
        sota_manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        proxy_count = sum(1 for t in manifest.get("tiles", []) if t.get("kind") == "osm-proxy")
        print(
            f"prepared SOTA manifest in {sota_dir}: "
            f"{manifest['tile_count']} tiles ({proxy_count} osm-proxy tiles)"
        )
    else:
        print(f"using cached SOTA models: {sota_manifest_path}")


if __name__ == "__main__":
    main()
