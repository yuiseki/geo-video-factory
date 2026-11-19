#!/usr/bin/env python3
"""Replace oversized Namba station / Namba Parks PLATEAU blocks with GSI+OSM city-proxy buildings."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import sys

import DracoPy
import numpy as np

ROOT = Path(__file__).resolve().parents[6]
FLYOVER = Path(__file__).resolve().parent
SRC_AREA = ROOT / "projects/2026/11/17/tour-shisaibashi-dotonbori-cosmosqare/areas/minami/assets"
SRC_CITY = SRC_AREA / "city"
DST_CITY = FLYOVER / "assets/city/minami_fixed"

sys.path.insert(0, str(ROOT / "packages/pipeline"))
import glb_spatial
from building_heights import calibrate_height_model, footprint_area_m2
from city_proxy import build_city_proxy_tile
from gsi_footprints import dem_sampler, fetch_gsi_buildings, orthophoto_texture
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

BBOX = [135.492, 34.660, 135.513, 34.680]


def strip_batch_ids_from_glb(glb_bytes: bytes, drop_batch_ids: set[int]) -> bytes:
    jlen = struct.unpack_from("<I", glb_bytes, 12)[0]
    gltf = json.loads(glb_bytes[20 : 20 + jlen])
    blen = struct.unpack_from("<I", glb_bytes, 20 + jlen)[0]
    bin_chunk = glb_bytes[28 + jlen : 28 + jlen + blen]

    prim = gltf["meshes"][0]["primitives"][0]
    ext = prim["extensions"]["KHR_draco_mesh_compression"]
    bv = gltf["bufferViews"][ext["bufferView"]]
    buf = bin_chunk[bv.get("byteOffset", 0) : bv.get("byteOffset", 0) + bv["byteLength"]]
    dm = DracoPy.decode(buf)

    pts = np.asarray(dm.points, dtype=np.float32)
    nrms = np.asarray(dm.normals, dtype=np.float32) if len(dm.normals) == len(pts) else np.zeros_like(pts)
    batch_attr = dm.get_attribute_by_unique_id(ext["attributes"]["_BATCHID"])
    bids = np.asarray(batch_attr["data"], dtype=np.float32).reshape(-1)
    faces = np.asarray(dm.faces, dtype=np.uint32).reshape(-1, 3)

    face_bids = bids[faces[:, 0]].astype(np.int64)
    keep_mask = ~np.isin(face_bids, list(drop_batch_ids))
    kept_faces = faces[keep_mask].reshape(-1).astype(np.uint32)

    pos_bytes = pts.tobytes()
    nrm_bytes = nrms.tobytes()
    bid_bytes = bids.tobytes()
    idx_bytes = kept_faces.tobytes()

    new_bin = bytearray()
    def add_view(raw: bytes, target: int) -> int:
        while len(new_bin) % 4:
            new_bin.append(0)
        off = len(new_bin)
        new_bin.extend(raw)
        idx = len(gltf["bufferViews"])
        gltf["bufferViews"].append({"buffer": 0, "byteOffset": off, "byteLength": len(raw), "target": target})
        return idx

    gltf["bufferViews"] = []
    gltf["accessors"] = []

    bv_pos = add_view(pos_bytes, 34962)
    bv_nrm = add_view(nrm_bytes, 34962)
    bv_bid = add_view(bid_bytes, 34962)
    bv_idx = add_view(idx_bytes, 34963)

    pmin = pts.min(axis=0).tolist()
    pmax = pts.max(axis=0).tolist()
    gltf["accessors"].append({"bufferView": bv_pos, "componentType": 5126, "count": len(pts), "type": "VEC3", "min": pmin, "max": pmax})
    gltf["accessors"].append({"bufferView": bv_nrm, "componentType": 5126, "count": len(pts), "type": "VEC3"})
    gltf["accessors"].append({"bufferView": bv_bid, "componentType": 5126, "count": len(pts), "type": "SCALAR"})
    gltf["accessors"].append({"bufferView": bv_idx, "componentType": 5125, "count": len(kept_faces), "type": "SCALAR"})

    prim["attributes"] = {"POSITION": 0, "NORMAL": 1, "_BATCHID": 2}
    prim["indices"] = 3
    prim.pop("extensions", None)
    for key in ("extensionsUsed", "extensionsRequired"):
        if key in gltf:
            gltf[key] = [x for x in gltf[key] if x != "KHR_draco_mesh_compression"]
            if not gltf[key]:
                gltf.pop(key)
    gltf["buffers"] = [{"byteLength": len(new_bin)}]

    jbytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    while len(jbytes) % 4:
        jbytes += b" "
    while len(new_bin) % 4:
        new_bin.append(0)
    total = 12 + 8 + len(jbytes) + 8 + len(new_bin)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(jbytes), b"JSON") + jbytes
        + struct.pack("<I4s", len(new_bin), b"BIN\0") + bytes(new_bin)
    )


def main() -> None:
    if DST_CITY.exists():
        shutil.rmtree(DST_CITY)
    DST_CITY.mkdir(parents=True)
    shutil.copytree(SRC_CITY / "models", DST_CITY / "models")
    manifest = json.loads((SRC_CITY / "manifest.json").read_text(encoding="utf-8"))

    # Remove old city-proxy and shadow tiles; keep PLATEAU tiles and filter oversized Namba blocks
    plateau_tiles = [t for t in manifest["tiles"] if t.get("kind") not in ("city-proxy", "city-shadow")]
    manifest["tiles"] = plateau_tiles

    dropped_ids: set[str] = set()
    plateau_heights: dict[str, dict] = {}
    for t in plateau_tiles:
        glb_path = DST_CITY / t["glb"]
        raw = glb_path.read_bytes()
        ids = t.get("ids", [])
        hs = glb_spatial.extract_glb_feature_heights(raw, t["rtc"], ids)
        drop_idx: set[int] = set()
        for i, gid in enumerate(ids):
            info = hs.get(gid)
            if not info:
                continue
            lon, lat = info["lonlat"]
            if 135.4998 <= lon <= 135.5028 and 34.6600 <= lat <= 34.6648 and info["height"] > 80.0:
                drop_idx.add(i)
                dropped_ids.add(gid)
        if drop_idx:
            print(f"Dropping {len(drop_idx)} oversized Namba blocks from {t['glb']}", flush=True)
            new_raw = strip_batch_ids_from_glb(raw, drop_idx)
            glb_path.write_bytes(new_raw)
            t["bytes"] = len(new_raw)
            for i in drop_idx:
                hs.pop(ids[i], None)
        plateau_heights.update(hs)

    print(f"Dropped {len(dropped_ids)} Namba blocks; remaining PLATEAU buildings: {len(plateau_heights)}", flush=True)

    # Rebuild city-proxy tile covering Namba station & Namba Parks with GSI + OSM
    cache = FLYOVER / "assets/minami_fixed_cache"
    cache.mkdir(parents=True, exist_ok=True)
    if (SRC_AREA / "gsi-cache").is_dir() and not (cache / "gsi-cache").exists():
        shutil.copytree(SRC_AREA / "gsi-cache", cache / "gsi-cache")
    footprints = fetch_gsi_buildings(BBOX, cache / "gsi-cache")
    ground = dem_sampler(BBOX, cache / "gsi-cache")

    tree = STRtree([shape(f["geometry"]) for f in footprints])
    samples, casters = [], {}
    for item in plateau_heights.values():
        hits = tree.query(Point(*item["lonlat"]), predicate="within")
        if len(hits):
            idx = int(hits[0])
            feat = footprints[idx]
            samples.append((feat["properties"]["vt_code"], footprint_area_m2(feat["geometry"]["coordinates"][0]), item["height"]))
            casters[idx] = max(casters.get(idx, 0.0), item["height"])

    import importlib.util
    sota_path = ROOT / "packages/renderer/test/e2e/prepare-buildings-tokyo-sota.py"
    spec = importlib.util.spec_from_file_location("sota", sota_path)
    assert spec and spec.loader
    sota = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sota)
    if os.environ.get("OVERPASS_URL"):
        sota.OVERPASS_ENDPOINTS = [os.environ["OVERPASS_URL"]]
    osm = sota.fetch_osm_buildings(BBOX, cache / "osm-buildings.geojson")

    roof_photo, roof_bounds = orthophoto_texture(BBOX, cache / "gsi-cache", zoom=18)
    roof_photo.save(DST_CITY / "roof-photo.jpg", quality=90)

    # Remove old city-proxy glbs
    for old in (DST_CITY / "models").glob("city-*.glb"):
        old.unlink()

    (DST_CITY / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = build_city_proxy_tile(
        footprints,
        BBOX,
        DST_CITY,
        ground=ground,
        orthophoto=roof_photo,
        orthophoto_bounds=roof_bounds,
        plateau_centroids=[item["lonlat"] for item in plateau_heights.values()],
        osm_features=osm,
        height_model=calibrate_height_model(samples),
        seed="osaka-minami-fixed-v1",
        shadow_casters=[(footprints[i], h) for i, h in sorted(casters.items())],
        roof_texture=("roof-photo.jpg", roof_bounds),
    )
    manifest["roof_texture"] = sota.roof_texture_entry("roof-photo.jpg", roof_bounds, manifest["center"])
    (DST_CITY / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared minami_fixed: {manifest['tile_count']} tiles, {manifest['city_proxy_building_count']} proxy buildings")


if __name__ == "__main__":
    main()
