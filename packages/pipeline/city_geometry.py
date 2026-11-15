"""Mesh building blocks for city proxies: walls, flat and pitched roofs, merged ground shadows.

Coordinates are local meters (x east, y north); vertices are written glTF Y-up as (x, z, -y).
See city_proxy.py for how they are assembled into a renderer tile.
"""
from __future__ import annotations

import json
import math
import struct

from osm_proxy import _triangulate_polygon

ROOF_OVERHANG_M = 0.35
# The renderer's sun stands at (-300, -450, 450) (east, north, up): shadows fall to the
# north-east, this many meters per meter of height. Keep in step with plateau-buildings.ts.
SHADOW_PER_M = (300 / 450, 450 / 450)
SHADOW_LIFT_M = 0.6
SHADOW_CELL_M = 40.0


def _srgb_to_linear(c: float) -> float:
    return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92


class _Mesh:
    def __init__(self) -> None:
        self.position: list[float] = []
        self.normal: list[float] = []
        self.color: list[float] = []
        self.uv: list[float] = []
        self.batch: list[float] = []
        self.style: list[float] = []

    def tri(self, a, b, c, color, uvs, batch: int, style: tuple[float, float], normal=None) -> None:
        if normal is None:
            ab = [b[i] - a[i] for i in range(3)]
            ac = [c[i] - a[i] for i in range(3)]
            n = [ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0]]
            length = math.sqrt(sum(v * v for v in n))
            if length < 1e-9:
                return
            normal = [v / length for v in n]
        lin = [_srgb_to_linear(v) for v in color]
        for point, uv in zip((a, b, c), uvs):
            self.position.extend(point)
            self.normal.extend(normal)
            self.color.extend(lin)
            self.uv.extend(uv)
            self.batch.append(float(batch))
            self.style.extend(style)

    def quad(self, a, b, c, d, color, uvs, batch, style) -> None:
        self.tri(a, b, c, color, (uvs[0], uvs[1], uvs[2]), batch, style)
        self.tri(a, c, d, color, (uvs[0], uvs[2], uvs[3]), batch, style)

    def glb(self) -> bytes:
        count = len(self.batch)
        binary = bytearray()
        views, accessors, attributes = [], [], {}

        def add(name: str, values: list[float], kind: str, width: int, with_bounds: bool = False) -> None:
            binary.extend(b'\0' * ((-len(binary)) % 4))
            data = struct.pack('<' + 'f' * len(values), *values)
            views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(data), 'target': 34962})
            binary.extend(data)
            accessor = {'bufferView': len(views) - 1, 'componentType': 5126, 'count': count, 'type': kind}
            if with_bounds:
                accessor['min'] = [min(values[i::width]) for i in range(width)]
                accessor['max'] = [max(values[i::width]) for i in range(width)]
            accessors.append(accessor)
            attributes[name] = len(accessors) - 1

        add('POSITION', self.position, 'VEC3', 3, True)
        add('NORMAL', self.normal, 'VEC3', 3)
        add('COLOR_0', self.color, 'VEC3', 3)
        add('TEXCOORD_0', self.uv, 'VEC2', 2)
        add('_BATCHID', self.batch, 'SCALAR', 1)
        add('_STYLE', self.style, 'VEC2', 2)
        document = {
            'asset': {'version': '2.0', 'generator': 'geo-video-factory city proxy'},
            'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0, 'name': 'city-proxy'}],
            'meshes': [{'name': 'city-proxy', 'primitives': [{'attributes': attributes, 'material': 0}]}],
            'materials': [{'name': 'city-proxy', 'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': 0, 'roughnessFactor': 0.9}}],
            'buffers': [{'byteLength': len(binary)}], 'bufferViews': views, 'accessors': accessors,
        }
        chunk = json.dumps(document, separators=(',', ':')).encode()
        chunk += b' ' * ((-len(chunk)) % 4)
        binary.extend(b'\0' * ((-len(binary)) % 4))
        total = 12 + 8 + len(chunk) + 8 + len(binary)
        return struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(chunk), b'JSON') + chunk + struct.pack('<I4s', len(binary), b'BIN\0') + bytes(binary)


def _walls(mesh: _Mesh, ring: list[tuple[float, float]], z0: float, z1: float, ground: float, color, batch, style, outer: bool) -> None:
    """Extrude one ring (meters, closed or open) from z0 to z1; the outside faces outward."""
    pts = ring[:-1] if ring[0] == ring[-1] else list(ring)
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if (area > 0) != outer:
        pts = pts[::-1]
    u = 0.0
    for i in range(len(pts)):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 1e-3:
            continue
        a, b = (x0, z0, -y0), (x1, z0, -y1)
        c, d = (x1, z1, -y1), (x0, z1, -y0)
        v0, v1 = z0 - ground, z1 - ground
        mesh.quad(a, b, c, d, color, ((u, v0), (u + length, v0), (u + length, v1), (u, v1)), batch, style)
        u += length


def _roof_triangles(rings: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Triangles covering a polygon with holes; constrained Delaunay where shapely has it."""
    import shapely
    from shapely.geometry import Polygon

    if hasattr(shapely, 'constrained_delaunay_triangles'):
        polygon = shapely.make_valid(Polygon(rings[0], rings[1:]))
        parts = [polygon] if polygon.geom_type == 'Polygon' else [g for g in getattr(polygon, 'geoms', []) if g.geom_type == 'Polygon']
        out = []
        for part in parts:
            for triangle in shapely.constrained_delaunay_triangles(part).geoms:
                out.append(list(triangle.exterior.coords)[:3])
        return out
    merged, triangles = _triangulate_polygon([[list(p) for p in ring] for ring in rings])
    return [[tuple(merged[n]) for n in tri] for tri in triangles]


def _flat_roof(mesh: _Mesh, rings: list[list[tuple[float, float]]], z: float, ground: float, color, batch, style) -> None:
    for triangle in _roof_triangles(rings):
        pts = [(x, z, -y) for x, y in triangle]
        # Facing up: counter-clockwise seen from above is clockwise in (x, -y).
        area = (pts[1][0] - pts[0][0]) * (pts[0][2] - pts[2][2]) - (pts[2][0] - pts[0][0]) * (pts[0][2] - pts[1][2])
        if area < 0:
            pts = [pts[0], pts[2], pts[1]]
        uvs = [(0.0, z - ground)] * 3
        mesh.tri(*pts, color, uvs, batch, style, normal=[0.0, 1.0, 0.0])


def _pitched(mesh: _Mesh, corners: list[tuple[float, float]], eave: float, ridge: float, ground: float, kind: str,
             wall, roof, batch, style) -> None:
    """Walls and roof of a pitched building on a rectangle (corners counter-clockwise)."""
    p = corners
    # Long axis from p0->p1 or p1->p2.
    if math.dist(p[0], p[1]) < math.dist(p[1], p[2]):
        p = p[1:] + p[:1]
    length, width = math.dist(p[0], p[1]), math.dist(p[1], p[2])
    ax = ((p[1][0] - p[0][0]) / length, (p[1][1] - p[0][1]) / length)
    ay = ((p[3][0] - p[0][0]) / width, (p[3][1] - p[0][1]) / width)
    center = (sum(c[0] for c in p) / 4, sum(c[1] for c in p) / 4)

    def at(s: float, t: float, z: float) -> tuple[float, float, float]:
        x = center[0] + ax[0] * s + ay[0] * t
        y = center[1] + ax[1] * s + ay[1] * t
        return (x, z, -y)

    hl, hw = length / 2, width / 2
    z0 = ground
    # Long walls up to the eave.
    _walls(mesh, [p[0], p[1], p[2], p[3], p[0]], z0, eave, ground, wall, batch, style, True)
    ridge_half = hl if kind == 'gable' else max(0.0, hl - hw)
    if kind == 'gable':
        # Gable triangles close the short ends above the eave.
        for sign in (-1, 1):
            a, b, c = at(sign * hl, -sign * hw, eave), at(sign * hl, sign * hw, eave), at(sign * hl, 0, ridge)
            mesh.tri(a, b, c, wall, ((0, eave - ground), (width, eave - ground), (hw, ridge - ground)), batch, style)
    o = ROOF_OVERHANG_M
    drop = o * (ridge - eave) / hw
    ze = eave - drop
    eh, ew = hl + o, hw + o
    rh = ridge_half + (o if kind == 'gable' else 0.0)
    v_e, v_r = ze - ground, ridge - ground
    for sign in (-1, 1):
        # Long roof planes (trapezoids for hip, rectangles for gable).
        a, b = at(-eh, sign * ew, ze), at(eh, sign * ew, ze)
        c, d = at(rh, 0, ridge), at(-rh, 0, ridge)
        quad = (a, b, c, d) if sign < 0 else (b, a, d, c)
        mesh.quad(*quad, roof, ((0, v_e), (1, v_e), (1, v_r), (0, v_r)), batch, style)
        if kind == 'hip':
            e, f, g = at(sign * eh, -ew, ze), at(sign * eh, ew, ze), at(sign * rh, 0, ridge)
            tri = (e, f, g) if sign > 0 else (f, e, g)
            mesh.tri(*tri, roof, ((0, v_e), (1, v_e), (0.5, v_r)), batch, style)


def _shadow_glb(casters, ground, lon0: float, lat0: float, kx: float, ky: float) -> bytes:
    """Ground shadows of every caster, merged so overlaps do not darken twice, cut into small
    cells so each triangle follows the terrain, lifted SHADOW_LIFT_M above the DEM."""
    import shapely
    from shapely.affinity import translate
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    pieces = []
    for rings, height in casters:
        footprint = shapely.make_valid(Polygon(rings[0], rings[1:]))
        if footprint.is_empty or height <= 0:
            continue
        dx, dy = SHADOW_PER_M[0] * height, SHADOW_PER_M[1] * height
        moved = translate(footprint, dx, dy)
        outer = list(Polygon(rings[0]).exterior.coords)
        if len(outer) <= 9:
            pieces.append(footprint.union(moved).convex_hull)
        else:
            sweeps = [Polygon([a, b, (b[0] + dx, b[1] + dy), (a[0] + dx, a[1] + dy)]).buffer(0) for a, b in zip(outer, outer[1:])]
            pieces.append(unary_union([footprint, moved, *sweeps]))
    if not pieces:
        return b''
    merged = unary_union(pieces)
    minx, miny, maxx, maxy = merged.bounds
    positions: list[float] = []
    x = math.floor(minx / SHADOW_CELL_M) * SHADOW_CELL_M
    while x < maxx:
        y = math.floor(miny / SHADOW_CELL_M) * SHADOW_CELL_M
        while y < maxy:
            cell = merged.intersection(box(x, y, x + SHADOW_CELL_M, y + SHADOW_CELL_M))
            for part in (cell.geoms if hasattr(cell, 'geoms') else [cell]):
                if part.geom_type != 'Polygon' or part.area <= 1e-6:
                    continue
                for triangle in shapely.constrained_delaunay_triangles(part).geoms:
                    for px, py in list(triangle.exterior.coords)[:3]:
                        z = ground(lon0 + px / kx, lat0 + py / ky) + SHADOW_LIFT_M
                        positions.extend((px, z, -py))
            y += SHADOW_CELL_M
        x += SHADOW_CELL_M
    if not positions:
        return b''
    binary = struct.pack('<' + 'f' * len(positions), *positions)
    count = len(positions) // 3
    document = {
        'asset': {'version': '2.0', 'generator': 'geo-video-factory city shadow'},
        'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0, 'name': 'city-shadow'}],
        'meshes': [{'name': 'city-shadow', 'primitives': [{'attributes': {'POSITION': 0}, 'material': 0}]}],
        'materials': [{'name': 'city-shadow', 'pbrMetallicRoughness': {'baseColorFactor': [0, 0, 0, 1]}}],
        'buffers': [{'byteLength': len(binary)}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(binary), 'target': 34962}],
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': count, 'type': 'VEC3',
                       'min': [min(positions[i::3]) for i in range(3)], 'max': [max(positions[i::3]) for i in range(3)]}],
    }
    chunk = json.dumps(document, separators=(',', ':')).encode()
    chunk += b' ' * ((-len(chunk)) % 4)
    total = 12 + 8 + len(chunk) + 8 + len(binary)
    return struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(chunk), b'JSON') + chunk + struct.pack('<I4s', len(binary), b'BIN\0') + binary
