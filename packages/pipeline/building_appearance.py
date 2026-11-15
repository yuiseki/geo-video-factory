"""Orthophoto-colored facade helpers and OSM-to-PLATEAU-compatible GLB proxies."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
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


def _varied_color(color: Iterable[int], rng: random.Random) -> str:
    red, green, blue = (max(0, min(255, int(value))) for value in color)
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


def extract_glb_feature_centroids(payload: bytes, rtc: list[float], tile_ids: list[str]) -> dict[str, list[float]]:
    """Read per-feature batch geometry centers as WGS84 points for OSM overlap rejection."""
    document, binary, _ = glb_chunks(payload)
    points: dict[int, list[tuple[float, float, float]]] = {}
    for mesh in document.get('meshes', []):
        for primitive in mesh.get('primitives', []):
            attributes = primitive.get('attributes', {})
            position_accessor = attributes.get('POSITION')
            feature_attribute = next((name for name in attributes if 'batchid' in name.lower() or 'featureid' in name.lower()), None)
            if position_accessor is None or feature_attribute is None:
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


def infer_glb_facade_colors(
    payload: bytes, rtc: list[float], tile_ids: list[str], orthophoto: Image.Image,
    bbox_degrees: list[float], *, seed: str = 'geo-video-factory',
) -> dict[str, str | None]:
    """Sample GSI orthophoto at per-feature GLB batch centroids and preserve textured IDs."""
    document, binary, _ = glb_chunks(payload)
    points: dict[int, list[tuple[float, float, float]]] = {}
    textured: set[int] = set()
    for mesh in document.get('meshes', []):
        for primitive in mesh.get('primitives', []):
            attributes = primitive.get('attributes', {})
            position_accessor = attributes.get('POSITION')
            feature_attribute = next((name for name in attributes if 'batchid' in name.lower() or 'featureid' in name.lower()), None)
            material_index = primitive.get('material')
            if material_index is not None:
                material = document.get('materials', [])[material_index]
                if material.get('pbrMetallicRoughness', {}).get('baseColorTexture'):
                    if feature_attribute:
                        for row in _accessor_values(document, binary, attributes[feature_attribute]):
                            if 0 <= int(round(row[0])) < len(tile_ids):
                                textured.add(int(round(row[0])))
                    else:
                        textured.update(range(len(tile_ids)))
                    continue
            if position_accessor is None or feature_attribute is None:
                continue
            positions = _accessor_values(document, binary, position_accessor)
            features = _accessor_values(document, binary, attributes[feature_attribute])
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
    for index, identifier in enumerate(tile_ids):
        if index in textured:
            buildings.append({'id': str(identifier), 'textured': True})
            continue
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
            if any(_inside_triangle(points[candidate], points[previous], points[current], points[following])
                   for candidate in indices if candidate not in (previous, current, following)):
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
    for building in buildings:
        ring = building['ring']
        points = ring[:-1] if ring[0] == ring[-1] else ring
        height = building['height']
        color = building['facade_color']
        rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        rgb = [((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in rgb]
        material_index = len(materials)
        materials.append({'name': str(building['id']), 'pbrMetallicRoughness': {'baseColorFactor': [*rgb, 1], 'metallicFactor': 0, 'roughnessFactor': 0.92}})
        ecef_points = [_ecef(lon, lat) for lon, lat in points]
        roof_points = [_ecef(lon, lat, height) for lon, lat in points]

        def gltf_local(point: tuple[float, float, float]) -> list[float]:
            dx, dy, dz = (point[i] - origin[i] for i in range(3))
            return [dx, dz, -dy]  # inverse of renderer's Y-up to ECEF-Z-up basis shim

        ground = [gltf_local(point) for point in ecef_points]
        roof = [gltf_local(point) for point in roof_points]
        positions: list[list[float]] = []
        normals: list[list[float]] = []
        indices: list[int] = []
        for tri in _triangulate(ring):
            _face(roof, tri, positions, normals, indices)
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
        pview = append_view(struct.pack('<' + 'f' * len(flat_positions), *flat_positions), 34962)
        nview = append_view(struct.pack('<' + 'f' * len(flat_normals), *flat_normals), 34962)
        iview = append_view(struct.pack('<' + 'I' * len(indices), *indices), 34963)
        paccessor = len(accessors)
        accessors.append({'bufferView': pview, 'componentType': 5126, 'count': len(positions), 'type': 'VEC3', 'min': [min(v[i] for v in positions) for i in range(3)], 'max': [max(v[i] for v in positions) for i in range(3)]})
        naccessor = len(accessors)
        accessors.append({'bufferView': nview, 'componentType': 5126, 'count': len(normals), 'type': 'VEC3'})
        iaccessor = len(accessors)
        accessors.append({'bufferView': iview, 'componentType': 5125, 'count': len(indices), 'type': 'SCALAR', 'min': [0], 'max': [len(positions) - 1]})
        mesh_index = len(meshes)
        meshes.append({'name': str(building['id']), 'primitives': [{'attributes': {'POSITION': paccessor, 'NORMAL': naccessor}, 'indices': iaccessor, 'material': material_index}], 'extras': {'osm_id': str(building['id'])}})
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


def _feature_rings(feature: dict[str, Any]) -> list[list[list[float]]]:
    geometry = feature.get('geometry') or {}
    if geometry.get('type') == 'Polygon':
        return geometry.get('coordinates') or []
    if geometry.get('type') == 'MultiPolygon':
        return [polygon[0] for polygon in geometry.get('coordinates') or [] if polygon]
    raise ValueError('OSM building proxy requires Polygon or MultiPolygon geometry')


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
    candidates: list[dict[str, Any]] = []
    for feature in features:
        identifier = str(feature.get('id') or (feature.get('properties') or {}).get('@id') or '')
        if not identifier or identifier in excluded:
            continue
        rings = _feature_rings(feature)
        if not rings:
            continue
        outer = rings[0]
        if len(outer) < 4 or outer[0] != outer[-1]:
            raise ValueError(f'OSM building {identifier} has an invalid closed polygon')
        centroid = (sum(p[0] for p in outer[:-1]) / (len(outer) - 1), sum(p[1] for p in outer[:-1]) / (len(outer) - 1))
        west, south, east, north = bbox_degrees
        if not (west <= centroid[0] <= east and south <= centroid[1] <= north):
            continue
        properties = dict(feature.get('properties') or {})
        height = _height(properties)
        color = properties.get('facade_color')
        if not color and orthophoto is not None:
            color = '#' + ''.join(f'{value:02x}' for value in sample_polygon_color(orthophoto, outer, bbox_degrees))
        candidates.append({'id': identifier, 'ring': outer, 'height': height, 'ortho_color': [183, 174, 159], 'facade_color': color})
    colored = assign_facade_colors(candidates, seed=seed)
    buildings = [{**building, 'facade_color': colored[index]['facade_color']} for index, building in enumerate(candidates)]
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
            'region': [math.radians(bbox_degrees[0]), math.radians(bbox_degrees[1]), math.radians(bbox_degrees[2]), math.radians(bbox_degrees[3]), 0, max(building['height'] for building in buildings)],
            'depth': 0,
            'extensions': [],
            'kind': 'osm-proxy',
        }
        manifest.setdefault('tiles', []).append(tile)
        all_ids = {str(identifier) for item in manifest['tiles'] for identifier in item.get('ids', [])}
        manifest['tile_count'] = len(manifest['tiles'])
        manifest['tile_ids'] = len(all_ids)
        manifest['total_bytes'] = sum(int(item.get('bytes', 0)) for item in manifest['tiles'])
        manifest['proxy_tile_count'] = sum(item.get('kind') == 'osm-proxy' for item in manifest['tiles'])
        manifest['proxy_building_count'] = sum(len(item.get('ids', [])) for item in manifest['tiles'] if item.get('kind') == 'osm-proxy')
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    else:
        manifest.setdefault('proxy_tile_count', 0)
        manifest.setdefault('proxy_building_count', 0)
    return manifest
