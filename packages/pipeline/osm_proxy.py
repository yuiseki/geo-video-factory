"""OSM building footprint extrusion to PLATEAU-compatible GLB proxy tiles."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any

from PIL import Image

from glb_spatial import _area, _ecef, _point_in_polygon


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
    orthophoto: Image.Image | None = None, kind: str = 'osm-proxy',
    plateau_footprints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Extrude OSM footprints to local GLB and append them to the renderer manifest."""
    from building_appearance import assign_facade_colors, sample_polygon_color

    if kind not in ('osm-proxy', 'citygml-proxy'):
        raise ValueError(f'unsupported building proxy kind: {kind}')
    footprint_tree = None
    footprint_shapes = []
    if kind == 'osm-proxy' and plateau_footprints is not None:
        from shapely.geometry import shape
        from shapely.strtree import STRtree
        for feature in plateau_footprints:
            geometry = feature.get('geometry')
            if geometry:
                polygon = shape(geometry)
                if not polygon.is_empty and polygon.is_valid and polygon.area > 0:
                    footprint_shapes.append(polygon)
        footprint_tree = STRtree(footprint_shapes)

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
        if kind == 'osm-proxy':
            if footprint_tree is not None:
                from shapely.geometry import shape
                polygon = shape(feature['geometry'])
                if not polygon.is_valid or polygon.area <= 0:
                    raise ValueError(f'OSM building {identifier} has invalid geometry')
                if any(polygon.intersection(footprint_shapes[int(i)]).area / polygon.area > 0.10 for i in footprint_tree.query(polygon)):
                    continue
            elif any(_point_in_polygon(point, poly) for poly in polygons for point in plateau_centroids):
                continue
        if not _polygons_intersect_bbox(polygons, bbox_degrees):
            continue
        height = _height(properties)
        explicit_color = properties.get('facade_color') or (properties.get('color') if kind == 'citygml-proxy' else None)
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
            'source': ('citygml://' if kind == 'citygml-proxy' else 'osm://') + (ids[0] if len(ids) == 1 else 'proxy/' + hashlib.sha256('\n'.join(ids).encode()).hexdigest()[:20]),
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
            'kind': kind,
        }
        manifest.setdefault('tiles', []).append(tile)
    all_ids = {str(identifier) for item in manifest.get('tiles', []) for identifier in item.get('ids', [])}
    manifest['tile_count'] = len(manifest.get('tiles', []))
    manifest['tile_ids'] = len(all_ids)
    manifest['total_bytes'] = sum(int(item.get('bytes', 0)) for item in manifest.get('tiles', []))
    manifest['proxy_tile_count'] = sum(item.get('kind') == 'osm-proxy' for item in manifest.get('tiles', []))
    manifest['proxy_building_count'] = sum(len(item.get('ids', [])) for item in manifest.get('tiles', []) if item.get('kind') == 'osm-proxy')
    manifest['citygml_proxy_building_count'] = sum(len(item.get('ids', [])) for item in manifest.get('tiles', []) if item.get('kind') == 'citygml-proxy')
    if buildings or manifest_path.exists():
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest
