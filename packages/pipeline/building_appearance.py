"""Orthophoto-colored facade helpers and re-exports for PLATEAU/OSM 3D buildings."""
from __future__ import annotations

import colorsys
import hashlib
import json
import math
from pathlib import Path
import random
import re
from typing import Any, Iterable

from PIL import Image

from glb_spatial import (
    WGS84_A,
    WGS84_E2,
    _accessor_values,
    _convex_hull,
    _decode_draco_primitive,
    _ecef,
    _feature_attribute,
    _geodetic,
    _has_buffer_view,
    _identity_mat4,
    _mesh_world_matrices,
    _transform_point,
    extract_glb_feature_centroids,
)
from osm_proxy import build_osm_proxy_tiles
from plateau_3d import glb_chunks

__all__ = [
    'WGS84_A',
    'WGS84_E2',
    '_accessor_values',
    '_ecef',
    '_geodetic',
    'apply_orthophoto_palette',
    'apply_citygml_colors',
    'assign_facade_colors',
    'build_osm_proxy_tiles',
    'build_plateau_facade_palette',
    'extract_glb_feature_centroids',
    'harmonize_orthophoto_color',
    'infer_glb_facade_colors',
    'sample_polygon_color',
]


def sample_polygon_color(image: Image.Image, polygon: list[list[float]], bbox_degrees: list[float]) -> tuple[int, int, int]:
    """Return the per-channel median of valid orthophoto pixels inside a lon/lat ring."""
    if len(bbox_degrees) != 4 or bbox_degrees[0] >= bbox_degrees[2] or bbox_degrees[1] >= bbox_degrees[3]:
        raise ValueError('bbox must be [west, south, east, north] with positive area')
    if len(polygon) < 4:
        raise ValueError('building polygon must be a closed ring with at least four points')
    west, south, east, north = bbox_degrees
    points = [((lon - west) / (east - west) * image.width, (north - lat) / (north - south) * image.height) for lon, lat in polygon]
    x0 = max(0, math.floor(min(x for x, _ in points)))
    x1 = min(image.width, math.ceil(max(x for x, _ in points)))
    y0 = max(0, math.floor(min(y for _, y in points)))
    y1 = min(image.height, math.ceil(max(y for _, y in points)))
    pixels = image.convert('RGB').load()
    samples: list[tuple[int, int, int]] = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            px, py = x + 0.5, y + 0.5
            inside = False
            for index in range(len(points) - 1):
                ax, ay = points[index]
                bx, by = points[index + 1]
                if (ay > py) != (by > py) and px < (bx - ax) * (py - ay) / ((by - ay) or 1e-15) + ax:
                    inside = not inside
            if inside:
                color = pixels[x, y]
                if max(color) >= 12:  # exclude transparent-image black/nodata after RGB conversion
                    samples.append(color)
    if not samples:
        raise ValueError('building polygon has no valid orthophoto pixels in the requested bbox')
    return tuple(sorted(channel)[len(samples) // 2] for channel in zip(*samples))


def harmonize_orthophoto_color(color: Iterable[int]) -> tuple[int, int, int]:
    """Compress bright roof highlights and clamp saturation for facade harmony."""
    r, g, b = (max(0, min(255, int(v))) / 255.0 for v in color)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = min(0.42, max(s * 1.12, 0.055))
    v = min(0.14 + 0.50 * (v ** 0.88), 0.52)
    hr, hg, hb = colorsys.hsv_to_rgb(h, s, v)
    return (round(hr * 255), round(hg * 255), round(hb * 255))


def _varied_color(color: Iterable[int], rng: random.Random) -> str:
    red, green, blue = harmonize_orthophoto_color(color)
    factor = rng.uniform(0.76, 1.19)
    tint = rng.choice(((1.035, 0.995, 0.94), (0.94, 0.99, 1.045), (1.015, 0.965, 1.03)))
    rgb = [max(35, min(238, round(value * factor * tint[index]))) for index, value in enumerate((red, green, blue))]
    return '#' + ''.join(f'{value:02x}' for value in rgb)


def assign_facade_colors(
    buildings: list[dict[str, Any]], *, seed: str = 'geo-video-factory',
    orthophoto: Image.Image | None = None, bbox_degrees: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Assign stable but varied colors to untextured buildings; textured ones are untouched."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, building in enumerate(buildings):
        item = dict(building)
        if item.get('textured') or item.get('texture'):
            result.append(item)
            continue
        color = item.get('ortho_color')
        if color is None and orthophoto is not None and bbox_degrees is not None:
            geometry = item.get('geometry') or {}
            coordinates = geometry.get('coordinates') or []
            if geometry.get('type') == 'MultiPolygon':
                ring = coordinates[0][0] if coordinates and coordinates[0] else []
            elif geometry.get('type') == 'Polygon':
                ring = coordinates[0] if coordinates else []
            else:
                ring = []
            if len(ring) >= 4:
                color = sample_polygon_color(orthophoto, ring, bbox_degrees)
        if color is None:
            color = (176, 169, 157)
        identity = str(item.get('id') or item.get('gml_id') or index)
        rng = random.Random(hashlib.sha256(f'{seed}:{identity}'.encode()).digest())
        facade = _varied_color(color, rng)
        attempt = 0
        # The finite RGB palette can be exhausted by large batches of similar roofs.
        # Bound retries so thousands of buildings cannot stall preparation forever.
        while facade in seen and attempt < 12:
            attempt += 1
            facade = _varied_color(color, random.Random(hashlib.sha256(f'{seed}:{identity}:{attempt}'.encode()).digest()))
        item['facade_color'] = facade
        seen.add(facade)
        result.append(item)
    return result


def build_plateau_facade_palette(
    tile_ids: list[str], footprints: dict[str, dict[str, Any]], orthophoto: Image.Image,
    bbox_degrees: list[float], *, textured_ids: set[str] | None = None,
    seed: str = 'geo-video-factory',
) -> dict[str, str | None]:
    """Map each PLATEAU feature ID to an ortho-derived facade tone, preserving textures."""
    textured = {str(value) for value in (textured_ids or set())}
    buildings: list[dict[str, Any]] = []
    for identifier in tile_ids:
        key = str(identifier)
        if key in textured:
            buildings.append({'id': key, 'textured': True})
            continue
        footprint = footprints.get(key)
        if footprint and footprint.get('type') == 'Feature':
            footprint = footprint.get('geometry')
        buildings.append({'id': key, 'geometry': footprint or {}, 'textured': False})
    colors = assign_facade_colors(buildings, seed=seed, orthophoto=orthophoto, bbox_degrees=bbox_degrees)
    return {str(building['id']): building.get('facade_color') for building in colors}


def apply_citygml_colors(output_dir: Path, features: list[dict[str, Any]]) -> dict[str, Any]:
    """Fill missing per-ID colors using previously sampled CityGML footprint colors."""
    colors = {}
    for feature in features:
        identifier = feature.get('id')
        color = (feature.get('properties') or {}).get('color')
        if identifier is not None and isinstance(color, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            colors[str(identifier)] = color
    path = output_dir / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    for tile in manifest['tiles']:
        ids = tile.get('ids') or []
        previous = tile.get('facade_colors') or []
        tile['facade_colors'] = [
            (previous[i] if i < len(previous) and previous[i] else colors.get(str(identifier)))
            for i, identifier in enumerate(ids)
        ]
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def _sample_point_color(image: Image.Image, longitude: float, latitude: float, bbox: list[float]) -> tuple[int, int, int]:
    west, south, east, north = bbox
    x = round((longitude - west) / (east - west) * image.width)
    y = round((north - latitude) / (north - south) * image.height)
    pixels = image.convert('RGB').load()
    samples = [pixels[px, py] for py in range(max(0, y - 2), min(image.height, y + 3))
               for px in range(max(0, x - 2), min(image.width, x + 3)) if max(pixels[px, py]) >= 12]
    if not samples:
        raise ValueError(f'no valid orthophoto pixels around ({longitude}, {latitude})')
    return tuple(sorted(channel)[len(samples) // 2] for channel in zip(*samples))


def infer_glb_facade_colors(
    payload: bytes, rtc: list[float], tile_ids: list[str], orthophoto: Image.Image,
    bbox_degrees: list[float], *, seed: str = 'geo-video-factory',
) -> dict[str, str | None]:
    """Sample GSI orthophoto at per-feature GLB batch centroids and preserve textured IDs."""
    document, binary, _ = glb_chunks(payload)
    mesh_matrices = _mesh_world_matrices(document)
    points: dict[int, list[tuple[float, float, float]]] = {}
    textured: set[int] = set()
    untextured: set[int] = set()
    for mesh_index, mesh in enumerate(document.get('meshes', [])):
        matrices = mesh_matrices.get(mesh_index) or [_identity_mat4()]
        for primitive in mesh.get('primitives', []):
            attributes = primitive.get('attributes', {})
            position_accessor = attributes.get('POSITION')
            feature_attribute = _feature_attribute(attributes)
            feature_accessor = attributes.get(feature_attribute) if feature_attribute else None
            material_index = primitive.get('material')
            has_texture = False
            if material_index is not None:
                material = document.get('materials', [])[material_index]
                has_texture = bool(material.get('pbrMetallicRoughness', {}).get('baseColorTexture'))
            draco_positions, draco_features = (None, None)
            if not _has_buffer_view(document, feature_accessor) or not _has_buffer_view(document, position_accessor):
                draco_positions, draco_features = _decode_draco_primitive(document, binary, primitive, feature_attribute)
            if has_texture:
                if _has_buffer_view(document, feature_accessor):
                    for row in _accessor_values(document, binary, feature_accessor):
                        feature_index = int(round(row[0]))
                        if 0 <= feature_index < len(tile_ids):
                            textured.add(feature_index)
                elif draco_features:
                    for row in draco_features:
                        feature_index = int(round(row[0]))
                        if 0 <= feature_index < len(tile_ids):
                            textured.add(feature_index)
                else:
                    textured.update(range(len(tile_ids)))
                continue
            if _has_buffer_view(document, feature_accessor):
                features = _accessor_values(document, binary, feature_accessor)
            elif draco_features:
                features = draco_features
            else:
                untextured.update(range(len(tile_ids)))
                continue
            for row in features:
                feature_index = int(round(row[0]))
                if 0 <= feature_index < len(tile_ids):
                    untextured.add(feature_index)
            if _has_buffer_view(document, position_accessor):
                positions = _accessor_values(document, binary, position_accessor)
            elif draco_positions is not None:
                positions = draco_positions
            else:
                continue
            if len(positions) != len(features):
                raise ValueError('GLB position and feature ID accessor counts differ')
            for matrix in matrices:
                for position, feature in zip(positions, features):
                    feature_index = int(round(feature[0]))
                    if not 0 <= feature_index < len(tile_ids):
                        continue
                    # PLATEAU GLB local coordinates become ECEF deltas through the same Y-up shim as the renderer.
                    wx, wy, wz = _transform_point(matrix, position)
                    ecef = (rtc[0] + wx, rtc[1] - wz, rtc[2] + wy)
                    points.setdefault(feature_index, []).append(ecef)
    fallback_origins = [
        (rtc[0] + m[0][3], rtc[1] - m[2][3], rtc[2] + m[1][3])
        for matrices in mesh_matrices.values() for m in matrices
    ]
    default_center = (
        (sum(p[0] for p in fallback_origins) / len(fallback_origins),
         sum(p[1] for p in fallback_origins) / len(fallback_origins),
         sum(p[2] for p in fallback_origins) / len(fallback_origins))
        if fallback_origins else (rtc[0], rtc[1], rtc[2])
    )
    centers = [
        (sum(point[0] for point in points[index]) / len(points[index]),
         sum(point[1] for point in points[index]) / len(points[index]),
         sum(point[2] for point in points[index]) / len(points[index]))
        if points.get(index) else default_center
        for index in range(len(tile_ids))
    ]
    buildings = []
    fully_textured = textured - untextured
    for index, identifier in enumerate(tile_ids):
        if index in fully_textured:
            buildings.append({'id': str(identifier), 'textured': True})
            continue
        color = None
        if points.get(index):
            hull = _convex_hull([_geodetic(pt) for pt in points[index]])
            if hull:
                try:
                    color = sample_polygon_color(orthophoto, hull, bbox_degrees)
                except ValueError:
                    color = None
        if color is None:
            longitude, latitude = _geodetic(centers[index])
            color = _sample_point_color(orthophoto, longitude, latitude, bbox_degrees)
        buildings.append({'id': str(identifier), 'ortho_color': color})
    assigned = assign_facade_colors(buildings, seed=seed)
    return {str(item['id']): item.get('facade_color') for item in assigned}


def apply_orthophoto_palette(
    output_dir: Path, orthophoto_path: Path, *, bbox_degrees: list[float] | None = None,
    seed: str = 'geo-video-factory',
) -> dict[str, Any]:
    """Add per-feature orthophoto facade colors to prepared PLATEAU model entries."""
    manifest_path = output_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    bbox = bbox_degrees or manifest['bbox_degrees']
    with Image.open(orthophoto_path) as source:
        image = source.convert('RGB')
    for tile in manifest['tiles']:
        if tile.get('kind') == 'osm-proxy' or not tile.get('ids'):
            continue
        model_path = output_dir / tile['glb']
        colors = infer_glb_facade_colors(model_path.read_bytes(), tile['rtc'], tile['ids'], image, bbox, seed=seed)
        tile['facade_colors'] = [colors.get(str(identifier)) for identifier in tile['ids']]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest
