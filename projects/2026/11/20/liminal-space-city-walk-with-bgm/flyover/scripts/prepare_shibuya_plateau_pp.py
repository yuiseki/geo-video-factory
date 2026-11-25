#!/usr/bin/env python3
"""PLATEAU++ for the Shibuya descent: every building the camera can see, with a texture.

    prepare_shibuya_plateau_pp.py <out dir> [--bbox=w,s,e,n] [--cache=dir]

1. PLATEAU 2025 LOD2 3D Tiles with their own photo textures, for every leaf tile in the box.
2. PLATEAU buildings without a texture: a facade colour from the GSI orthophoto, the orthophoto on the roof.
3. Buildings PLATEAU does not model: GSI footprints (OSM height and levels where tagged), heights calibrated
   on the PLATEAU buildings, the orthophoto on the roof (city proxy).

The same steps as the buildings-tokyo-sota E2E preparer, for another box; its helpers are reused, not copied.
Needs packages/pipeline/requirements-dev.txt. Set OVERPASS_URL to your own Overpass instance.
Run under the host's resource limits."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[7]
sys.path.insert(0, str(REPO / "packages/pipeline"))
_spec = importlib.util.spec_from_file_location(
    "prepare_sota", REPO / "packages/renderer/test/e2e/prepare-buildings-tokyo-sota.py")
sota = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sota)

# about 1 km around the scramble crossing: the whole top-down view at the hand-over zoom and the far side
# of the pitched views at the end of the descent
BBOX = [139.6895, 35.6505, 139.7115, 35.6685]
SEED = "shibuya-plateau-pp-v1"


def main(argv: list[str]) -> None:
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    out = Path([a for a in argv if not a.startswith("--")][0]).resolve()
    bbox = [float(v) for v in opts["bbox"].split(",")] if "bbox" in opts else BBOX
    from buildings.plateau_3d import prepare_tiles
    from buildings.building_appearance import apply_orthophoto_palette
    from buildings.building_heights import calibrate_height_model, footprint_area_m2
    from buildings.city_proxy import build_city_proxy_tile, wall_hex
    from buildings.glb_spatial import extract_glb_feature_heights
    from buildings.gsi_footprints import dem_sampler, fetch_gsi_buildings, orthophoto_texture
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    cache = Path(opts["cache"]).resolve() if "cache" in opts else out.parent / (out.name + "-cache")
    plateau_dir = out
    if not (plateau_dir / "manifest.json").exists():
        m = prepare_tiles(sota.TILESET_URL, bbox, plateau_dir, max_texture_dimension=2048,
                          far_texture_dimension=1024, workers=3)
        if not m.get("tiles"):
            raise SystemExit("no PLATEAU tiles in the box")
        print(f"PLATEAU: {m['tile_count']} tiles, {m['tile_ids']} buildings")

    m = json.loads((plateau_dir / "manifest.json").read_text(encoding="utf-8"))
    ortho_bbox = list(bbox)
    for tile in m["tiles"]:
        reg = tile.get("region")
        if isinstance(reg, list) and len(reg) >= 4:
            ortho_bbox = [min(ortho_bbox[0], math.degrees(reg[0])), min(ortho_bbox[1], math.degrees(reg[1])),
                          max(ortho_bbox[2], math.degrees(reg[2])), max(ortho_bbox[3], math.degrees(reg[3]))]
    cache.mkdir(parents=True, exist_ok=True)
    _, ortho_bounds = sota.prepare_orthophoto(ortho_bbox, cache / "ortho.png", cache / "ortho_bounds.json")
    m = apply_orthophoto_palette(plateau_dir, cache / "ortho.png", bbox_degrees=ortho_bounds, seed=SEED)

    footprints = fetch_gsi_buildings(bbox, cache / "gsi")
    ground = dem_sampler(bbox, cache / "gsi")
    plateau = {}
    for tile in m["tiles"]:
        plateau.update(extract_glb_feature_heights((plateau_dir / tile["glb"]).read_bytes(), tile["rtc"], tile["ids"]))
    polygons = [shape(f["geometry"]) for f in footprints]
    tree = STRtree(polygons)
    samples, casters = [], {}
    for item in plateau.values():
        hits = tree.query(Point(*item["lonlat"]), predicate="within")
        if len(hits):
            f = footprints[int(hits[0])]
            samples.append((f["properties"]["vt_code"], footprint_area_m2(f["geometry"]["coordinates"][0]), item["height"]))
            casters[int(hits[0])] = max(casters.get(int(hits[0]), 0.0), item["height"])
    for tile in m["tiles"]:
        tile["facade_colors"] = [wall_hex(str(i), plateau.get(str(i), {}).get("height", 6.0)) for i in tile["ids"]]
    (plateau_dir / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    model = calibrate_height_model(samples)
    print(f"GSI footprints {len(footprints)}, PLATEAU buildings {len(plateau)}, calibration samples {len(samples)}")

    osm = sota.fetch_osm_buildings(bbox, cache / "osm-buildings.geojson")
    roof, roof_bounds = orthophoto_texture(bbox, cache / "gsi", zoom=18)
    roof.save(plateau_dir / "roof-photo.jpg", quality=90)
    m = build_city_proxy_tile(
        footprints, bbox, plateau_dir, ground=ground, orthophoto=roof, orthophoto_bounds=roof_bounds,
        plateau_centroids=[item["lonlat"] for item in plateau.values()], osm_features=osm, height_model=model,
        seed=SEED, shadow_casters=[(footprints[i], h) for i, h in sorted(casters.items())],
        roof_texture=("roof-photo.jpg", roof_bounds))
    m["plateau_building_count"] = len(plateau)
    m["roof_texture"] = sota.roof_texture_entry("roof-photo.jpg", roof_bounds, m["center"])
    (plateau_dir / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PLATEAU++: {m['tile_count']} tiles, {len(plateau)} PLATEAU buildings, "
          f"{m['city_proxy_building_count']} proxy buildings")


if __name__ == "__main__":
    main(sys.argv[1:])
