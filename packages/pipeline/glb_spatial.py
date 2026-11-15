"""GLB/glTF spatial decoding, node hierarchy transforms, and WGS84 coordinate helpers."""
from __future__ import annotations

import math
import re
import struct
from typing import Any

try:
    import DracoPy
except ImportError:  # optional runtime acceleration for Draco-compressed GLBs
    DracoPy = None

from plateau_3d import glb_chunks

WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3


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


def _ecef(lon: float, lat: float, height: float = 0) -> tuple[float, float, float]:
    lam, phi = math.radians(lon), math.radians(lat)
    sin_phi = math.sin(phi)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_phi * sin_phi)
    return (
        (n + height) * math.cos(phi) * math.cos(lam),
        (n + height) * math.cos(phi) * math.sin(lam),
        (n * (1 - WGS84_E2) + height) * sin_phi,
    )


def _area(ring: list[list[float]]) -> float:
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def _feature_attribute(attributes: dict[str, Any]) -> str | None:
    return next((name for name in attributes if re.search(r'batch.?id|feature.?id', name, re.I)), None)


def _has_buffer_view(document: dict[str, Any], accessor_index: int | None) -> bool:
    if accessor_index is None:
        return False
    accessors = document.get('accessors', [])
    return 0 <= accessor_index < len(accessors) and 'bufferView' in accessors[accessor_index]


def _decode_draco_primitive(
    document: dict[str, Any], binary: bytes, primitive: dict[str, Any], feature_attribute: str | None,
) -> tuple[list[tuple[float, ...]], list[tuple[float, ...]]] | tuple[None, None]:
    ext = (primitive.get('extensions') or {}).get('KHR_draco_mesh_compression')
    if DracoPy is None or not ext or ext.get('bufferView') is None:
        return None, None
    buffer_views = document.get('bufferViews') or []
    bv_index = int(ext['bufferView'])
    if not (0 <= bv_index < len(buffer_views)):
        return None, None
    view = buffer_views[bv_index]
    start = int(view.get('byteOffset', 0))
    compressed = binary[start:start + int(view['byteLength'])]
    if not compressed:
        return None, None
    mesh = DracoPy.decode(compressed)
    draco_attrs = ext.get('attributes') or {}
    pos_attr = mesh.get_attribute_by_unique_id(int(draco_attrs['POSITION'])) if 'POSITION' in draco_attrs else None
    raw_positions = pos_attr['data'] if pos_attr is not None else getattr(mesh, 'points', None)
    if raw_positions is None:
        return None, None
    positions = [tuple(float(v) for v in row[:3]) for row in raw_positions]
    if feature_attribute and feature_attribute in draco_attrs:
        feat_attr = mesh.get_attribute_by_unique_id(int(draco_attrs[feature_attribute]))
        if feat_attr is not None:
            features = [(float(row[0]) if hasattr(row, '__len__') else float(row),) for row in feat_attr['data']]
            return positions, features
    return positions, []


def _identity_mat4() -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def _mat4_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _node_local_matrix(node: dict[str, Any]) -> list[list[float]]:
    if 'matrix' in node:
        m = [float(v) for v in node['matrix']]
        return [[m[col * 4 + row] for col in range(4)] for row in range(4)]
    tx, ty, tz = (float(v) for v in node.get('translation', (0.0, 0.0, 0.0)))
    qx, qy, qz, qw = (float(v) for v in node.get('rotation', (0.0, 0.0, 0.0, 1.0)))
    sx, sy, sz = (float(v) for v in node.get('scale', (1.0, 1.0, 1.0)))
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    return [
        [(1.0 - 2.0 * (yy + zz)) * sx, 2.0 * (xy - wz) * sy, 2.0 * (xz + wy) * sz, tx],
        [2.0 * (xy + wz) * sx, (1.0 - 2.0 * (xx + zz)) * sy, 2.0 * (yz - wx) * sz, ty],
        [2.0 * (xz - wy) * sx, 2.0 * (yz + wx) * sy, (1.0 - 2.0 * (xx + yy)) * sz, tz],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _mesh_world_matrices(document: dict[str, Any]) -> dict[int, list[list[list[float]]]]:
    nodes = document.get('nodes') or []
    if not nodes:
        return {index: [_identity_mat4()] for index in range(len(document.get('meshes', [])))}
    scenes = document.get('scenes') or []
    scene_index = int(document.get('scene', 0))
    if 0 <= scene_index < len(scenes) and scenes[scene_index].get('nodes'):
        roots = [int(i) for i in scenes[scene_index]['nodes']]
    else:
        children = {int(c) for n in nodes for c in n.get('children', [])}
        roots = [i for i in range(len(nodes)) if i not in children]
    result: dict[int, list[list[list[float]]]] = {}

    def visit(node_index: int, parent: list[list[float]]) -> None:
        node = nodes[node_index]
        world = _mat4_mul(parent, _node_local_matrix(node))
        if 'mesh' in node:
            result.setdefault(int(node['mesh']), []).append(world)
        for child in node.get('children', []):
            visit(int(child), world)

    for root in roots:
        visit(root, _identity_mat4())
    return result


def _transform_point(matrix: list[list[float]], point: tuple[float, ...]) -> tuple[float, float, float]:
    x, y, z = float(point[0]), float(point[1]), float(point[2])
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    )


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
    mesh_matrices = _mesh_world_matrices(document)
    points: dict[int, list[tuple[float, float, float]]] = {}
    for mesh_index, mesh in enumerate(document.get('meshes', [])):
        matrices = mesh_matrices.get(mesh_index) or [_identity_mat4()]
        for primitive in mesh.get('primitives', []):
            attributes = primitive.get('attributes', {})
            position_accessor = attributes.get('POSITION')
            feature_attribute = _feature_attribute(attributes)
            feature_accessor = attributes.get(feature_attribute) if feature_attribute else None
            if _has_buffer_view(document, position_accessor) and _has_buffer_view(document, feature_accessor):
                positions = _accessor_values(document, binary, position_accessor)
                features = _accessor_values(document, binary, feature_accessor)
            else:
                positions, features = _decode_draco_primitive(document, binary, primitive, feature_attribute)
                if positions is None or not features:
                    continue
            if len(positions) != len(features):
                raise ValueError('GLB position and feature ID accessor counts differ')
            for matrix in matrices:
                for position, feature in zip(positions, features):
                    index = int(round(feature[0]))
                    if 0 <= index < len(tile_ids):
                        wx, wy, wz = _transform_point(matrix, position)
                        points.setdefault(index, []).append((rtc[0] + wx, rtc[1] - wz, rtc[2] + wy))
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
