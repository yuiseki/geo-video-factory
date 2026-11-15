"""Orthophoto-colored facade helpers and OSM-to-PLATEAU-compatible GLB proxies."""
from __future__ import annotations

import colorsys
import hashlib
import json
import math
from pathlib import Path
import random
import re
import struct
from typing import Any, Iterable

from PIL import Image

from plateau_3d import glb_chunks

WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3


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
        while facade in seen:
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


def _accessor_values(document: dict[str, Any], binary: bytes, accessor_index: int) -> list[tuple[float, ...]]:
    accessor = document['accessors'][accessor_index]
    view = document['bufferViews'][accessor['bufferView']]
    component = {5121: ('B', 1), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}.get(accessor['componentType'])
    if not component:
        raise ValueError(f'unsupported GLB accessor component type: {accessor["componentType"]}')
    code, width = component
    components = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}.get(accessor['type'])
    if not components:
        raise ValueError(f'unsupported GLB accessor type: {accessor["type"]}')
    stride = int(view.get('byteStride', width * components))
    start = int(view.get('byteOffset', 0)) + int(accessor.get('byteOffset', 0))
    rows = []
    for row in range(int(accessor['count'])):
        offset = start + row * stride
        if offset + width * components > len(binary):
            raise ValueError('GLB accessor points outside the binary chunk')
        rows.append(struct.unpack_from('<' + code * components, binary, offset))
    return rows


def _geodetic(ecef: tuple[float, float, float]) -> tuple[float, float]:
    x, y, z = ecef
    longitude = math.atan2(y, x)
    p = math.hypot(x, y)
    latitude = math.atan2(z, p * (1 - WGS84_E2))
    for _ in range(8):
        sin_latitude = math.sin(latitude)
        n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_latitude * sin_latitude)
        latitude = math.atan2(z + WGS84_E2 * n * sin_latitude, p)
    return math.degrees(longitude), math.degrees(latitude)


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


def _feature_attribute(attributes: dict[str, Any]) -> str | None:
    return next((name for name in attributes if re.search(r'batch.?id|feature.?id', name, re.I)), None)


def _has_buffer_view(document: dict[str, Any], accessor_index: int | None) -> bool:
    if accessor_index is None:
        return False
    accessors = document.get('accessors', [])
    return 0 <= accessor_index < len(accessors) and 'bufferView' in accessors[accessor_index]


def _convex_hull(points: list[tuple[float, float]]) -> list[list[float]]:
    unique = sorted(set(points))
    if len(unique) < 3:
        return []

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return []
    ring = [[p[0], p[1]] for p in hull] + [[hull[0][0], hull[0][1]]]
    return ring if abs(_area(ring)) > 1e-14 else []


def extract_glb_feature_centroids(payload: bytes, rtc: list[float], tile_ids: list[str]) -> dict[str, list[float]]:
    """Read per-feature batch geometry centers as WGS84 points for OSM overlap rejection."""
    document, binary, _ = glb_chunks(payload)
    points: dict[int, list[tuple[float, float, float]]] = {}
    for mesh in document.get('meshes', []):
        for primitive in mesh.get('primitives', []):
            attributes = primitive.get('attributes', {})
            position_accessor = attributes.get('POSITION')
            feature_attribute = _feature_attribute(attributes)
            if not _has_buffer_view(document, position_accessor) or not _has_buffer_view(document, attributes.get(feature_attribute or '')):
                continue
            positions = _accessor_values(document, binary, position_accessor)
            features = _accessor_values(document, binary, attributes[feature_attribute])
            if len(positions) != len(features):
                raise ValueError('GLB position and feature ID accessor counts differ')
            for position, feature in zip(positions, features):
                index = int(round(feature[0]))
                if 0 <= index < len(tile_ids):
                    points.setdefault(index, []).append((rtc[0] + position[0], rtc[1] - position[2], rtc[2] + position[1]))
    result: dict[str, list[float]] = {}
    for index, identifier in enumerate(tile_ids):
        vertices = points.get(index)
        if vertices:
            mean = tuple(sum(vertex[axis] for vertex in vertices) / len(vertices) for axis in range(3))
            result[str(identifier)] = list(_geodetic(mean))
    return result


def _point_in_ring(point: tuple[float, float], ring: list[list[float]]) -> bool:
    longitude, latitude = point
    inside = False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index]
        x2, y2 = ring[index + 1]
        if (y1 > latitude) != (y2 > latitude) and longitude < (x2 - x1) * (latitude - y1) / ((y2 - y1) or 1e-15) + x1:
            inside = not inside
    return inside


def _point_in_polygon(point: tuple[float, float], rings: list[list[list[float]]]) -> bool:
    if not rings or not _point_in_ring(point, rings[0]):
        return False
    return not any(_point_in_ring(point, hole) for hole in rings[1:])


def infer_glb_facade_colors(
    payload: bytes, rtc: list[float], tile_ids: list[str], orthophoto: Image.Image,
    bbox_degrees: list[float], *, seed: str = 'geo-video-factory',
) -> dict[str, str | None]:
    """Sample GSI orthophoto at per-feature GLB batch centroids and preserve textured IDs."""
    document, binary, _ = glb_chunks(payload)
    points: dict[int, list[tuple[float, float, float]]] = {}
    textured: set[int] = set()
    untextured: set[int] = set()
    for mesh in document.get('meshes', []):
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
            if has_texture:
                if _has_buffer_view(document, feature_accessor):
                    for row in _accessor_values(document, binary, feature_accessor):
                        feature_index = int(round(row[0]))
                        if 0 <= feature_index < len(tile_ids):
                            textured.add(feature_index)
                else:
                    textured.update(range(len(tile_ids)))
                continue
            if _has_buffer_view(document, feature_accessor):
                features = _accessor_values(document, binary, feature_accessor)
                for row in features:
                    feature_index = int(round(row[0]))
                    if 0 <= feature_index < len(tile_ids):
                        untextured.add(feature_index)
            else:
                untextured.update(range(len(tile_ids)))
                continue
            if not _has_buffer_view(document, position_accessor):
                continue
            positions = _accessor_values(document, binary, position_accessor)
            if len(positions) != len(features):
                raise ValueError('GLB position and feature ID accessor counts differ')
            for position, feature in zip(positions, features):
                feature_index = int(round(feature[0]))
                if not 0 <= feature_index < len(tile_ids):
                    continue
                # PLATEAU GLB local coordinates become ECEF deltas through the same Y-up shim as the renderer.
                ecef = (rtc[0] + position[0], rtc[1] - position[2], rtc[2] + position[1])
                points.setdefault(feature_index, []).append(ecef)
    centers = [
        (sum(point[0] for point in points[index]) / len(points[index]),
         sum(point[1] for point in points[index]) / len(points[index]),
         sum(point[2] for point in points[index]) / len(points[index]))
        if points.get(index) else (rtc[0], rtc[1], rtc[2])
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


def _ecef(lon: float, lat: float, height: float = 0) -> tuple[float, float, float]:
    lam, phi = math.radians(lon), math.radians(lat)
    sin_phi = math.sin(phi)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_phi * sin_phi)
    return (
        (n + height) * math.cos(phi) * math.cos(lam),
        (n + height) * math.cos(phi) * math.sin(lam),
        (n * (1 - WGS84_E2) + height) * sin_phi,
    )


def _height(properties: dict[str, Any]) -> float:
    raw = properties.get('height')
    try:
        if raw is not None:
            value = float(str(raw).strip().lower().removesuffix('meters').removesuffix('meter').removesuffix('m').strip())
            if math.isfinite(value) and value > 0:
                return value
    except (TypeError, ValueError):
        pass
    raw_levels = properties.get('building:levels', properties.get('levels'))
    try:
        levels = float(raw_levels)
        if math.isfinite(levels) and levels > 0:
            return levels * 3.0
    except (TypeError, ValueError):
        pass
    raise ValueError('OSM building requires a positive height or building:levels')


def _area(ring: list[list[float]]) -> float:
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def _cross(a: list[float], b: list[float], c: list[float]) -> float:
    return (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])


def _inside_triangle(p: list[float], a: list[float], b: list[float], c: list[float]) -> bool:
    crosses = (_cross(a, b, p), _cross(b, c, p), _cross(c, a, p))
    return all(value >= -1e-14 for value in crosses) or all(value <= 1e-14 for value in crosses)


def _ensure_ccw(ring: list[list[float]], ccw: bool = True) -> list[list[float]]:
    points = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
    if len(points) < 3:
        raise ValueError('OSM building polygon must have at least three vertices')
    closed = points + [points[0]]
    area = _area(closed)
    if abs(area) < 1e-14:
        raise ValueError('OSM building polygon must have positive area')
    if (area < 0) == ccw:
        points = list(reversed(points))
    return points


def _segments_intersect(a: list[float], b: list[float], c: list[float], d: list[float]) -> bool:
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    return ((d1 > 1e-12 and d2 < -1e-12) or (d1 < -1e-12 and d2 > 1e-12)) and \
           ((d3 > 1e-12 and d4 < -1e-12) or (d3 < -1e-12 and d4 > 1e-12))


def _merge_hole(outer: list[list[float]], hole: list[list[float]]) -> list[list[float]]:
    m_idx = max(range(len(hole)), key=lambda i: (hole[i][0], hole[i][1]))
    mx, my = hole[m_idx]
    best_x = float('inf')
    best_edge = (0, 1)
    for i in range(len(outer)):
        a = outer[i]
        b = outer[(i + 1) % len(outer)]
        if (a[1] <= my <= b[1] or b[1] <= my <= a[1]) and abs(b[1] - a[1]) > 1e-15:
            t = (my - a[1]) / (b[1] - a[1])
            ix = a[0] + t * (b[0] - a[0])
            if ix >= mx - 1e-12 and ix < best_x:
                best_x = ix
                best_edge = (i, (i + 1) % len(outer))
    i0, i1 = best_edge
    p_idx = i0 if outer[i0][0] >= outer[i1][0] else i1
    # Check if any outer vertex lies inside the triangle (M, I, P) and is closer in angle
    ix_pt = [best_x, my]
    for idx, cand in enumerate(outer):
        if idx in (i0, i1) or cand[0] < mx:
            continue
        if _inside_triangle(cand, [mx, my], ix_pt, outer[p_idx]):
            if not any(_segments_intersect([mx, my], cand, outer[j], outer[(j + 1) % len(outer)]) for j in range(len(outer))):
                p_idx = idx
    return outer[:p_idx + 1] + hole[m_idx:] + hole[:m_idx + 1] + [outer[p_idx]] + outer[p_idx + 1:]


def _triangulate_polygon(rings: list[list[list[float]]]) -> tuple[list[list[float]], list[tuple[int, int, int]]]:
    outer = _ensure_ccw(rings[0], ccw=True)
    holes = [_ensure_ccw(hole, ccw=False) for hole in rings[1:] if len(hole) >= 4]
    holes.sort(key=lambda h: max(pt[0] for pt in h), reverse=True)
    merged = list(outer)
    for hole in holes:
        merged = _merge_hole(merged, hole)
    return merged, _triangulate(merged + [merged[0]])


def _triangulate(ring: list[list[float]]) -> list[tuple[int, int, int]]:
    points = ring[:-1] if ring[0] == ring[-1] else ring
    if len(points) < 3 or abs(_area(ring)) < 1e-14:
        raise ValueError('OSM building polygon must have positive area')
    indices = list(range(len(points)))
    if _area(ring) < 0:
        indices.reverse()
    triangles: list[tuple[int, int, int]] = []
    while len(indices) > 3:
        found = False
        for position, current in enumerate(indices):
            previous = indices[position - 1]
            following = indices[(position + 1) % len(indices)]
            if _cross(points[previous], points[current], points[following]) <= 1e-14:
                continue
            if any(
                points[candidate] not in (points[previous], points[current], points[following])
                and _inside_triangle(points[candidate], points[previous], points[current], points[following])
                for candidate in indices if candidate not in (previous, current, following)
            ):
                continue
            triangles.append((previous, current, following))
            indices.pop(position)
            found = True
            break
        if not found:
            raise ValueError('OSM building polygon cannot be triangulated')
    triangles.append(tuple(indices))
    return triangles


def _face(vertices: list[list[float]], indices: tuple[int, int, int], positions: list[list[float]], out_normals: list[list[float]], out_indices: list[int]) -> None:
    a, b, c = (vertices[index] for index in indices)
    ab = [b[i] - a[i] for i in range(3)]
    ac = [c[i] - a[i] for i in range(3)]
    normal = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]]
    length = math.sqrt(sum(value * value for value in normal)) or 1
    normal = [value / length for value in normal]
    start = len(positions)
    positions.extend([vertices[index] for index in indices])
    out_normals.extend([normal, normal, normal])
    out_indices.extend((start, start + 1, start + 2))


def _glb_for_buildings(buildings: list[dict[str, Any]], origin: tuple[float, float, float]) -> bytes:
    binary = bytearray()
    buffer_views: list[dict[str, int]] = []
    accessors: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    meshes: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    for building_index, building in enumerate(buildings):
        polygons = building.get('polygons') or [[building['ring']]]
        height = building['height']
        color = building['facade_color']
        rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        rgb = [((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in rgb]
        material_index = len(materials)
        materials.append({'name': str(building['id']), 'pbrMetallicRoughness': {'baseColorFactor': [*rgb, 1], 'metallicFactor': 0, 'roughnessFactor': 0.92}})

        def gltf_local(point: tuple[float, float, float]) -> list[float]:
            dx, dy, dz = (point[i] - origin[i] for i in range(3))
            return [dx, dz, -dy]  # inverse of renderer's Y-up to ECEF-Z-up basis shim

        positions: list[list[float]] = []
        normals: list[list[float]] = []
        indices: list[int] = []
        for poly_rings in polygons:
            merged_pts, roof_tris = _triangulate_polygon(poly_rings)
            roof_merged = [gltf_local(_ecef(lon, lat, height)) for lon, lat in merged_pts]
            for tri in roof_tris:
                _face(roof_merged, tri, positions, normals, indices)
            for ring_idx, ring in enumerate(poly_rings):
                if len(ring) < 4:
                    continue
                ordered = _ensure_ccw(ring, ccw=(ring_idx == 0))
                ground = [gltf_local(_ecef(lon, lat)) for lon, lat in ordered]
                roof = [gltf_local(_ecef(lon, lat, height)) for lon, lat in ordered]
                for index in range(len(ground)):
                    next_index = (index + 1) % len(ground)
                    _face(ground + roof, (index, next_index, next_index + len(ground)), positions, normals, indices)
                    _face(ground + roof, (index, next_index + len(ground), index + len(ground)), positions, normals, indices)

        def append_view(data: bytes, target: int) -> int:
            binary.extend(b'\0' * ((-len(binary)) % 4))
            offset = len(binary)
            binary.extend(data)
            view_index = len(buffer_views)
            buffer_views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data), 'target': target})
            return view_index

        flat_positions = [value for vertex in positions for value in vertex]
        flat_normals = [value for vertex in normals for value in vertex]
        batch_ids = [float(building_index)] * len(positions)
        pview = append_view(struct.pack('<' + 'f' * len(flat_positions), *flat_positions), 34962)
        nview = append_view(struct.pack('<' + 'f' * len(flat_normals), *flat_normals), 34962)
        bview = append_view(struct.pack('<' + 'f' * len(batch_ids), *batch_ids), 34962)
        iview = append_view(struct.pack('<' + 'I' * len(indices), *indices), 34963)
        paccessor = len(accessors)
        accessors.append({'bufferView': pview, 'componentType': 5126, 'count': len(positions), 'type': 'VEC3', 'min': [min(v[i] for v in positions) for i in range(3)], 'max': [max(v[i] for v in positions) for i in range(3)]})
        naccessor = len(accessors)
        accessors.append({'bufferView': nview, 'componentType': 5126, 'count': len(normals), 'type': 'VEC3'})
        baccessor = len(accessors)
        accessors.append({'bufferView': bview, 'componentType': 5126, 'count': len(batch_ids), 'type': 'SCALAR'})
        iaccessor = len(accessors)
        accessors.append({'bufferView': iview, 'componentType': 5125, 'count': len(indices), 'type': 'SCALAR', 'min': [0], 'max': [len(positions) - 1]})
        mesh_index = len(meshes)
        meshes.append({'name': str(building['id']), 'primitives': [{'attributes': {'POSITION': paccessor, 'NORMAL': naccessor, '_BATCHID': baccessor}, 'indices': iaccessor, 'material': material_index}], 'extras': {'osm_id': str(building['id'])}})
        nodes.append({'mesh': mesh_index, 'name': str(building['id'])})

    document = {
        'asset': {'version': '2.0', 'generator': 'geo-video-factory OSM proxy pipeline'},
        'scene': 0,
        'scenes': [{'nodes': list(range(len(nodes)))}],
        'nodes': nodes,
        'meshes': meshes,
        'materials': materials,
        'buffers': [{'byteLength': len(binary)}],
        'bufferViews': buffer_views,
        'accessors': accessors,
    }
    json_chunk = json.dumps(document, separators=(',', ':')).encode('utf-8')
    json_chunk += b' ' * ((-len(json_chunk)) % 4)
    binary.extend(b'\0' * ((-len(binary)) % 4))
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(json_chunk), b'JSON') + json_chunk + struct.pack('<I4s', len(binary), b'BIN\0') + binary


def _feature_polygons(feature: dict[str, Any]) -> list[list[list[list[float]]]]:
    geometry = feature.get('geometry') or {}
    if geometry.get('type') == 'Polygon':
        coords = geometry.get('coordinates') or []
        return [coords] if coords else []
    if geometry.get('type') == 'MultiPolygon':
        return [polygon for polygon in geometry.get('coordinates') or [] if polygon]
    raise ValueError('OSM building proxy requires Polygon or MultiPolygon geometry')


def _polygons_intersect_bbox(polygons: list[list[list[list[float]]]], bbox_degrees: list[float]) -> bool:
    west, south, east, north = bbox_degrees
    xs = [pt[0] for poly in polygons for pt in poly[0]]
    ys = [pt[1] for poly in polygons for pt in poly[0]]
    if not xs or not ys:
        return False
    return max(xs) >= west and min(xs) <= east and max(ys) >= south and min(ys) <= north


def build_osm_proxy_tiles(
    features: list[dict[str, Any]], bbox_degrees: list[float], output_dir: Path,
    *, plateau_ids: set[str] | None = None, seed: str = 'geo-video-factory',
    orthophoto: Image.Image | None = None,
) -> dict[str, Any]:
    """Extrude OSM footprints to local GLB and append them to the renderer manifest."""
    if len(bbox_degrees) != 4 or bbox_degrees[0] >= bbox_degrees[2] or bbox_degrees[1] >= bbox_degrees[3]:
        raise ValueError('bbox must be [west, south, east, north] with positive area')
    output_dir.mkdir(parents=True, exist_ok=True)
    models_dir = output_dir / 'models'
    models_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {
        'format': 'geo-video-factory.plateau-3d/1', 'tileset_url': None, 'bbox_degrees': bbox_degrees,
        'center': [(bbox_degrees[0] + bbox_degrees[2]) / 2, (bbox_degrees[1] + bbox_degrees[3]) / 2],
        'tile_count': 0, 'tile_ids': 0, 'total_source_bytes': 0, 'total_bytes': 0,
        'texture_max_dimension': None, 'tiles': [],
    }
    if manifest.get('format') != 'geo-video-factory.plateau-3d/1':
        raise ValueError('existing manifest does not use the renderer-compatible PLATEAU tile schema')
    existing_ids = {str(identifier) for tile in manifest.get('tiles', []) for identifier in tile.get('ids', [])}
    excluded = existing_ids | {str(value) for value in (plateau_ids or set())}
    plateau_centroids: list[tuple[float, float]] = []
    for tile in manifest.get('tiles', []):
        centroids = tile.get('feature_centroids') or {}
        if isinstance(centroids, dict):
            for coord in centroids.values():
                if isinstance(coord, (list, tuple)) and len(coord) >= 2:
                    plateau_centroids.append((float(coord[0]), float(coord[1])))
    candidates: list[dict[str, Any]] = []
    for feature in features:
        identifier = str(feature.get('id') or (feature.get('properties') or {}).get('@id') or '')
        if not identifier or identifier in excluded:
            continue
        properties = dict(feature.get('properties') or {})
        if properties.get('building') in ('no', False):
            continue
        polygons = _feature_polygons(feature)
        if not polygons:
            continue
        for poly in polygons:
            outer = poly[0]
            if len(outer) < 4 or outer[0] != outer[-1]:
                raise ValueError(f'OSM building {identifier} has an invalid closed polygon')
        if any(_point_in_polygon(point, poly) for poly in polygons for point in plateau_centroids):
            continue
        if not _polygons_intersect_bbox(polygons, bbox_degrees):
            continue
        height = _height(properties)
        explicit_color = properties.get('facade_color')
        ortho_color = list(sample_polygon_color(orthophoto, polygons[0][0], bbox_degrees)) if (not explicit_color and orthophoto is not None) else [183, 174, 159]
        candidates.append({'id': identifier, 'polygons': polygons, 'ring': polygons[0][0], 'height': height, 'ortho_color': ortho_color, 'explicit_facade_color': explicit_color})
    colored = assign_facade_colors(candidates, seed=seed)
    buildings = [{**building, 'facade_color': building['explicit_facade_color'] or colored[index]['facade_color']} for index, building in enumerate(candidates)]
    if buildings:
        center = manifest.get('center') or [(bbox_degrees[0] + bbox_degrees[2]) / 2, (bbox_degrees[1] + bbox_degrees[3]) / 2]
        rtc = _ecef(center[0], center[1])
        glb = _glb_for_buildings(buildings, rtc)
        digest = hashlib.sha256(glb).hexdigest()
        model_path = models_dir / f'osm-proxy-{digest[:20]}.glb'
        model_path.write_bytes(glb)
        ids = [building['id'] for building in buildings]
        tile = {
            'source': 'osm://' + ids[0] if len(ids) == 1 else 'osm://proxy/' + hashlib.sha256('\n'.join(ids).encode()).hexdigest()[:20],
            'glb': model_path.relative_to(output_dir).as_posix(),
            'sha256': digest,
            'source_sha256': hashlib.sha256(json.dumps(features, sort_keys=True, default=str).encode()).hexdigest(),
            'source_bytes': 0,
            'bytes': len(glb),
            'rtc': list(rtc),
            'ids': ids,
            'facade_colors': [building['facade_color'] for building in buildings],
            'region': [math.radians(bbox_degrees[0]), math.radians(bbox_degrees[1]), math.radians(bbox_degrees[2]), math.radians(bbox_degrees[3]), 0, max(building['height'] for building in buildings)],
            'depth': 0,
            'extensions': [],
            'kind': 'osm-proxy',
        }
        manifest.setdefault('tiles', []).append(tile)
    all_ids = {str(identifier) for item in manifest.get('tiles', []) for identifier in item.get('ids', [])}
    manifest['tile_count'] = len(manifest.get('tiles', []))
    manifest['tile_ids'] = len(all_ids)
    manifest['total_bytes'] = sum(int(item.get('bytes', 0)) for item in manifest.get('tiles', []))
    manifest['proxy_tile_count'] = sum(item.get('kind') == 'osm-proxy' for item in manifest.get('tiles', []))
    manifest['proxy_building_count'] = sum(len(item.get('ids', [])) for item in manifest.get('tiles', []) if item.get('kind') == 'osm-proxy')
    if buildings or manifest_path.exists():
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest
