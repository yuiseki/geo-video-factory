#!/usr/bin/env python3
"""Prepare the Asakusa–Ryogoku city with the buildings-tokyo-sota pipeline."""
from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'packages/pipeline'))

from building_appearance import apply_orthophoto_palette
from building_heights import calibrate_height_model, footprint_area_m2
from city_proxy import build_city_proxy_tile, wall_hex
from glb_spatial import extract_glb_feature_heights
from gsi_footprints import dem_sampler, fetch_gsi_buildings, orthophoto_texture
from plateau_3d import prepare_tiles
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

BBOX = [139.783, 35.685, 139.806, 35.719]
TILESET = 'https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13-bldg-lod2-texture-2025/tileset.json'


def main() -> None:
    helpers_path = ROOT / 'packages/renderer/test/e2e/prepare-buildings-tokyo-sota.py'
    spec = importlib.util.spec_from_file_location('sota_preparation', helpers_path)
    assert spec and spec.loader
    sota = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sota)
    if os.environ.get('OVERPASS_URL'):
        sota.OVERPASS_ENDPOINTS = [os.environ['OVERPASS_URL']]
    assets = PROJECT / 'assets'
    city = assets / 'city'
    manifest_path = city / 'manifest.json'
    assets.mkdir(parents=True, exist_ok=True)
    if sota.cache_is_complete(manifest_path, require_sota=True):
        print('Using prepared city', manifest_path, flush=True)
        return
    if not sota.cache_is_complete(manifest_path):
        prepare_tiles(TILESET, BBOX, city, max_texture_dimension=2048, far_texture_dimension=1024, workers=3)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    ortho_bbox = list(BBOX)
    for tile in manifest['tiles']:
        region = tile.get('region')
        if isinstance(region, list) and len(region) >= 4:
            for i in range(2):
                ortho_bbox[i] = min(ortho_bbox[i], math.degrees(region[i]))
                ortho_bbox[i + 2] = max(ortho_bbox[i + 2], math.degrees(region[i + 2]))
    photo_path = assets / 'ortho.png'
    _, bounds = sota.prepare_orthophoto(ortho_bbox, photo_path, assets / 'ortho_bounds.json')
    manifest = apply_orthophoto_palette(city, photo_path, bbox_degrees=bounds, seed='asakusa-ryogoku-v1')
    print('Preparing GSI footprints and DEM', flush=True)
    cache = assets / 'gsi-cache'
    footprints = fetch_gsi_buildings(BBOX, cache)
    ground = dem_sampler(BBOX, cache)
    plateau = {}
    for tile in manifest['tiles']:
        plateau.update(extract_glb_feature_heights((city / tile['glb']).read_bytes(), tile['rtc'], tile['ids']))
    if not plateau:
        raise RuntimeError('No PLATEAU building heights could be decoded; install DracoPy')
    tree = STRtree([shape(feature['geometry']) for feature in footprints])
    samples, casters = [], {}
    for item in plateau.values():
        hits = tree.query(Point(*item['lonlat']), predicate='within')
        if len(hits):
            i = int(hits[0])
            feature = footprints[i]
            samples.append((feature['properties']['vt_code'], footprint_area_m2(feature['geometry']['coordinates'][0]), item['height']))
            casters[i] = max(casters.get(i, 0.0), item['height'])
    for tile in manifest['tiles']:
        tile['facade_colors'] = [wall_hex(str(i), plateau.get(str(i), {}).get('height', 6.0)) for i in tile.get('ids', [])]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PLATEAU buildings: {len(plateau)}, GSI footprints: {len(footprints)}, height samples: {len(samples)}', flush=True)
    osm = sota.fetch_osm_buildings(BBOX, assets / 'osm-buildings.geojson')
    roof_photo, roof_bounds = orthophoto_texture(BBOX, cache, zoom=18)
    roof_photo.save(city / 'roof-photo.jpg', quality=90)
    manifest = build_city_proxy_tile(
        footprints, BBOX, city, ground=ground, orthophoto=roof_photo, orthophoto_bounds=roof_bounds,
        plateau_centroids=[item['lonlat'] for item in plateau.values()], osm_features=osm,
        height_model=calibrate_height_model(samples), seed='asakusa-ryogoku-v1',
        shadow_casters=[(footprints[i], height) for i, height in sorted(casters.items())],
        roof_texture=('roof-photo.jpg', roof_bounds),
    )
    manifest['sota_prepared'] = sota.SOTA_VERSION
    manifest['plateau_building_count'] = len(plateau)
    manifest['roof_texture'] = sota.roof_texture_entry('roof-photo.jpg', roof_bounds, manifest['center'])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Prepared {manifest['tile_count']} tiles and {manifest['city_proxy_building_count']} proxy buildings", flush=True)


if __name__ == '__main__':
    main()
