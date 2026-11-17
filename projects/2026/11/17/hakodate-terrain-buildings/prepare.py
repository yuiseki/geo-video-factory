#!/usr/bin/env python3
"""函館山北側から函館駅周辺の建物を地理院データから用意する。"""
from pathlib import Path
import importlib.util
import json
import os
import sys

PROJECT = Path(__file__).resolve().parent
REPO = PROJECT.parents[4]
PIPELINE = REPO / 'packages' / 'pipeline'
sys.path.insert(0, str(PIPELINE))
from building_heights import calibrate_height_model
from city_proxy import build_city_proxy_tile
from gsi_footprints import fetch_gsi_buildings, dem_sampler, orthophoto_texture

BBOX = [140.69, 41.755, 140.78, 41.805]
ASSETS = PROJECT / 'assets'
CACHE = ASSETS / 'cache'
OUT = ASSETS / 'city'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / 'manifest.json'
    if manifest.exists():
        print(f'using cached {manifest}', flush=True)
        return
    print('Fetching GSI building footprints', flush=True)
    buildings = fetch_gsi_buildings(BBOX, CACHE)
    print(f'GSI building footprints: {len(buildings)}', flush=True)
    if not buildings:
        raise RuntimeError('No GSI building footprints were found')
    print('Fetching GSI DEM', flush=True)
    ground = dem_sampler(BBOX, CACHE)
    print('Fetching GSI aerial photo (zoom 16)', flush=True)
    image, bounds = orthophoto_texture(BBOX, CACHE, zoom=16)
    image.save(OUT / 'roof-photo.jpg', quality=90)
    osm_path = ASSETS / 'osm-buildings.geojson'
    runner = REPO / 'packages/renderer/test/e2e/prepare-buildings-tokyo-sota.py'
    spec = importlib.util.spec_from_file_location('gvf_osm_fetch', runner)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print('Fetching OSM building attributes', flush=True)
    osm = module.fetch_osm_buildings(BBOX, osm_path)
    print(f'OSM building footprints: {len(osm)}', flush=True)
    print('Generating buildings and ground-aligned shadows', flush=True)
    data = build_city_proxy_tile(buildings, BBOX, OUT, ground=ground,
        orthophoto=image, orthophoto_bounds=bounds, osm_features=osm,
        height_model=calibrate_height_model([]), seed='hakodate-v1',
        roof_texture=('roof-photo.jpg', bounds))
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f"Generated buildings: {data.get('city_proxy_building_count')}", flush=True)

if __name__ == '__main__':
    main()
