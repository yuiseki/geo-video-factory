"""Turn complete building footprints into one renderer tile of stand-in buildings.

For footprints that PLATEAU does not model (typically the GSI `BldA` outlines from
`gsi_footprints`), this writes a single GLB in which every building shares one mesh and one
material, so tens of thousands of buildings cost one draw call and one shader program:

- the base sits on the GSI DEM the renderer drapes (`ground(lon, lat)`), slightly sunk;
- the height comes from `building_heights.estimate_height` (OSM tags first, then a model
  calibrated on PLATEAU; never below one story);
- small, nearly rectangular ordinary buildings get a pitched roof (gable 切妻 or hip 寄棟,
  chosen per building from its ID), built on the footprint's minimum rotated rectangle;
- the roof color is the median orthophoto color inside the footprint (what is really seen from
  above); the walls get a plausible facade color by structure class (an estimate);
- vertex attributes carry what the renderer's shader needs: COLOR_0, TEXCOORD_0 = (meters along
  the wall, meters above the building's ground), _BATCHID = building index, _STYLE = (style,
  eave height). Styles: 0 house, 1 sturdy / RC, 2 roof without walls.

Positions are written in a local east-up-south frame around the manifest center (glTF Y-up:
x = east, y = altitude, z = -north, meters), with absolute orthometric altitude, and the tile is
marked `frame: "enu"`. Pitched roofs, facade colors and windows are illustrations, not survey data.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from building_heights import ONE_STORY_M, calibrate_height_model, estimate_height, footprint_area_m2
from glb_spatial import _ecef
from city_geometry import SHADOW_CELL_M, SHADOW_LIFT_M, SHADOW_PER_M, _flat_roof, _Mesh, _pitched, _shadow_glb, _walls  # noqa: F401

GROUND_SINK_M = 0.4

PITCHED_AREA_M2 = (25.0, 260.0)
PITCHED_MIN_RECTANGULARITY = 0.82
HOUSE_WALLS = ['#ece7dc', '#e2dacb', '#d9d3c8', '#d1c7b5', '#e8dfcd', '#cbc1b0', '#bcae9a', '#dadad5', '#c2c6c4', '#ab9d8b', '#f0ebe0', '#d6cbb8']
RC_WALLS = ['#d2cdc3', '#c0baaf', '#d8d2c6', '#aca69d', '#cabca6', '#bba88f', '#9f9283', '#ded9cf', '#b3b6b5']
SHED_WALLS = ['#8f8c86', '#9b968c', '#7f7c75']


def _hash01(identifier: str, salt: str) -> float:
    return int(hashlib.sha256(f'{salt}:{identifier}'.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _hex_rgb(value: str) -> tuple[float, float, float]:
    return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))


def wall_color(identifier: str, style: int) -> tuple[float, float, float]:
    palette = SHED_WALLS if style == 2 else RC_WALLS if style == 1 else HOUSE_WALLS
    r, g, b = _hex_rgb(palette[int(_hash01(identifier, 'wall') * len(palette)) % len(palette)])
    k = 0.94 + 0.10 * _hash01(identifier, 'wall-v')
    return (min(1, r * k), min(1, g * k), min(1, b * k))


def wall_hex(identifier: str, height: float) -> str:
    """Facade color for a building modelled elsewhere (e.g. untextured PLATEAU), matching the proxies."""
    r, g, b = wall_color(identifier, 1 if height >= 10 else 0)
    return '#' + ''.join(f'{round(v * 255):02x}' for v in (r, g, b))


def roof_color(sample: tuple[int, int, int] | None, identifier: str) -> tuple[float, float, float]:
    """Orthophoto roof color, with haze and blown highlights pulled back a little."""
    if sample is None:
        grey = 0.32 + 0.18 * _hash01(identifier, 'roof')
        return (grey, grey * 0.98, grey * 0.96)
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in sample))
    v = min(0.86, max(0.16, 0.08 + 0.92 * v))
    s = min(0.8, s * 1.35)
    return colorsys.hsv_to_rgb(h, s, v)


def _ortho_sampler(orthophoto: Image.Image | None, bbox: list[float]):
    if orthophoto is None:
        return lambda ring: None
    from building_appearance import sample_polygon_color

    def sample(ring):
        try:
            return sample_polygon_color(orthophoto, ring, bbox)
        except ValueError:
            return None
    return sample


def build_city_proxy_tile(
    features: list[dict[str, Any]], bbox_degrees: list[float], output_dir: Path, *,
    ground: Callable[[float, float], float],
    orthophoto: Image.Image | None = None,
    plateau_centroids: list[list[float]] | None = None,
    osm_features: list[dict[str, Any]] | None = None,
    height_model: dict[str, Any] | None = None,
    seed: str = 'geo-video-factory',
    shadow_casters: list[tuple[dict[str, Any], float]] | None = None,
    roof_texture: tuple[str, list[float]] | None = None,
) -> dict[str, Any]:
    """Append one `city-proxy` tile for footprints PLATEAU lacks; returns the manifest."""
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'models').mkdir(exist_ok=True)
    manifest_path = output_dir / 'manifest.json'
    center = [(bbox_degrees[0] + bbox_degrees[2]) / 2, (bbox_degrees[1] + bbox_degrees[3]) / 2]
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {
        'format': 'geo-video-factory.plateau-3d/1', 'tileset_url': None, 'bbox_degrees': bbox_degrees,
        'center': center, 'tile_count': 0, 'tile_ids': 0, 'total_source_bytes': 0, 'total_bytes': 0,
        'texture_max_dimension': None, 'tiles': [],
    }
    manifest['tiles'] = [t for t in manifest.get('tiles', []) if t.get('kind') not in ('city-proxy', 'city-shadow')]
    center = manifest.get('center') or center
    lon0, lat0 = center
    kx = 111_320.0 * math.cos(math.radians(lat0))
    ky = 110_950.0
    model = height_model or calibrate_height_model([])
    sample_roof = _ortho_sampler(orthophoto, bbox_degrees)

    polygons = [shape(f['geometry']) for f in features]
    plateau_hits: set[int] = set()
    if plateau_centroids:
        tree = STRtree(polygons)
        for lon, lat in plateau_centroids:
            for index in tree.query(Point(lon, lat), predicate='within'):
                plateau_hits.add(int(index))
    osm_shapes = [shape(f['geometry']) for f in (osm_features or [])]
    osm_tree = STRtree(osm_shapes) if osm_shapes else None

    mesh = _Mesh()
    records: list[dict[str, Any]] = []
    local = lambda ring: [((lon - lon0) * kx, (lat - lat0) * ky) for lon, lat in ring]
    casters: list[tuple[list[list[tuple[float, float]]], float]] = []
    for extra, extra_height in shadow_casters or []:
        casters.append(([local(r) for r in extra['geometry']['coordinates']], extra_height))
    for index, (feat, polygon) in enumerate(zip(features, polygons)):
        if index in plateau_hits or polygon.is_empty or polygon.area <= 0:
            continue
        identifier = str(feat.get('id'))
        props = dict(feat.get('properties') or {})
        if osm_tree is not None:
            best, best_share = None, 0.5
            for j in osm_tree.query(polygon):
                share = polygon.intersection(osm_shapes[int(j)]).area / polygon.area
                if share > best_share:
                    best, best_share = int(j), share
            if best is not None:
                tags = osm_features[best].get('properties') or {}
                for key in ('height', 'building:levels', 'building', 'roof:shape'):
                    if key in tags:
                        props[key] = tags[key]
        outer = feat['geometry']['coordinates'][0]
        area = footprint_area_m2(outer)
        height, source = estimate_height(props, area, model, identifier)
        code = str(props.get('vt_code') or '3101')
        style = 2 if code in ('3111', '3112') else 1 if code in ('3102', '3103') else 0
        ground_samples = [ground(lon, lat) for lon, lat in outer[:-1]] + [ground(*polygon.centroid.coords[0])]
        base = min(ground_samples) - GROUND_SINK_M
        top = base + GROUND_SINK_M + (max(ground_samples) - min(ground_samples)) + height
        rings = [local(ring) for ring in feat['geometry']['coordinates']]
        casters.append((rings, top - base - GROUND_SINK_M))
        wall = wall_color(identifier, style)
        roof = roof_color(sample_roof(outer), identifier)
        batch = len(records)

        roof_kind = 'flat'
        if style == 0 and PITCHED_AREA_M2[0] <= area <= PITCHED_AREA_M2[1] and len(rings) == 1 and props.get('roof:shape', 'auto') != 'flat':
            from shapely.geometry import Polygon
            footprint_m = Polygon(rings[0])
            rect = footprint_m.minimum_rotated_rectangle
            if rect.geom_type == 'Polygon' and footprint_m.area / rect.area >= PITCHED_MIN_RECTANGULARITY:
                roof_kind = 'gable' if _hash01(identifier, f'{seed}:roof') < 0.45 else 'hip'
                corners = list(rect.exterior.coords)[:4]
                if sum(corners[i][0] * corners[(i + 1) % 4][1] - corners[(i + 1) % 4][0] * corners[i][1] for i in range(4)) < 0:
                    corners = corners[::-1]
                width = min(math.dist(corners[0], corners[1]), math.dist(corners[1], corners[2]))
                pitch = math.radians(22 + 9 * _hash01(identifier, 'pitch'))
                rise = min(width / 2 * math.tan(pitch), max(0.6, height - 2.5))
                eave = top - rise
                _pitched(mesh, corners, eave, top, base, roof_kind, wall, roof, batch, (float(style), eave - base))
        if roof_kind == 'flat':
            for ring_index, ring in enumerate(rings):
                _walls(mesh, ring, base, top, base, wall, batch, (float(style), top - base), ring_index == 0)
            _flat_roof(mesh, rings, top, base, roof, batch, (float(style), top - base))
        records.append({'id': identifier, 'height': round(top - base - GROUND_SINK_M, 2), 'source': source, 'roof': roof_kind,
                        'ground': round(base, 2), 'vt_code': code})

    if records:
        glb = mesh.glb()
        digest = hashlib.sha256(glb).hexdigest()
        model_path = output_dir / 'models' / f'city-proxy-{digest[:20]}.glb'
        model_path.write_bytes(glb)
        sidecar = output_dir / f'city-proxy-{digest[:20]}.buildings.json'
        sidecar.write_text(json.dumps({'height_model': model, 'buildings': records}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
        sources: dict[str, int] = {}
        for record in records:
            key = record['source'].split(':')[0]
            sources[key] = sources.get(key, 0) + 1
        texture = None
        if roof_texture:
            image, (tw, ts, te, tn) = roof_texture
            texture = {'image': image, 'bounds': [tw, ts, te, tn],
                       'bounds_m': [(tw - lon0) * kx, (ts - lat0) * ky, (te - lon0) * kx, (tn - lat0) * ky]}
        manifest['tiles'].append({
            'source': 'gsi-footprints://' + digest[:20], 'kind': 'city-proxy', 'frame': 'enu',
            **({'roof_texture': texture} if texture else {}),
            'glb': model_path.relative_to(output_dir).as_posix(), 'buildings': sidecar.name,
            'sha256': digest, 'bytes': len(glb), 'rtc': list(_ecef(lon0, lat0)),
            'ids': [r['id'] for r in records], 'height_sources': sources,
            'region': [math.radians(v) for v in bbox_degrees] + [min(r['ground'] for r in records), max(r['ground'] + GROUND_SINK_M + r['height'] for r in records)],
            'depth': 0, 'extensions': [],
        })
    if casters:
        shadow = _shadow_glb(casters, ground, lon0, lat0, kx, ky)
        if shadow:
            digest = hashlib.sha256(shadow).hexdigest()
            shadow_path = output_dir / 'models' / f'city-shadow-{digest[:20]}.glb'
            shadow_path.write_bytes(shadow)
            manifest['tiles'].append({
                'source': 'shadow://' + digest[:20], 'kind': 'city-shadow', 'frame': 'enu',
                'glb': shadow_path.relative_to(output_dir).as_posix(), 'sha256': digest, 'bytes': len(shadow),
                'rtc': list(_ecef(lon0, lat0)), 'ids': [], 'region': [math.radians(v) for v in bbox_degrees] + [0, 0],
                'depth': 0, 'extensions': [], 'shadow_per_m': list(SHADOW_PER_M),
            })
    tiles = manifest['tiles']
    manifest['tile_count'] = len(tiles)
    manifest['tile_ids'] = len({str(i) for t in tiles for i in t.get('ids', [])})
    manifest['total_bytes'] = sum(int(t.get('bytes', 0)) for t in tiles)
    manifest['city_proxy_building_count'] = len(records)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest
