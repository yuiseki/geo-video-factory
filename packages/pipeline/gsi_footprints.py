"""Complete building footprints and ground heights from GSI (地理院) tiles.

PLATEAU covers only part of Japan, and OpenStreetMap footprints are patchy outside big
cities. The GSI optimal vector tiles (`optimal_bvmap-v1`, layer `BldA`) carry the building
outlines of the 1:2,500 / 1:25,000 base map with a structure class (`vt_code`):

  3101 普通建物 (ordinary)   3102 堅ろう建物 (sturdy, usually RC)
  3103 高層建物 (high-rise)  3111 普通無壁舎 / 3112 堅ろう無壁舎 (roofed, no walls)

A building that crosses a tile edge arrives as one piece per tile; `fetch_gsi_buildings`
joins those pieces again. `dem_sampler` reads the same `dem_png` tiles the renderer drapes as
terrain, so a footprint can be set on the ground the viewer actually sees.

Source: 国土地理院 ベクトルタイル / 標高タイル (地理院タイル利用規約, attribution required).
"""
from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path
import struct
import time
from typing import Any, Callable
import urllib.error
import urllib.request

BVMAP_URL = 'https://cyberjapandata.gsi.go.jp/xyz/optimal_bvmap-v1/{z}/{x}/{y}.pbf'
DEM_URL = 'https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png'
PHOTO_URL = 'https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg'
Fetch = Callable[[str], 'bytes | None']


def default_fetch(url: str) -> bytes | None:
    """GET a tile; None for 404 (no data there), retry other failures a few times."""
    last: Exception | None = None
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'geo-video-factory/1.0'})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            last = error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last = error
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'tile fetch failed: {url}: {last}')


# --- Mapbox Vector Tile decoding (only what the GSI tiles use) ------------------------------

def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _fields(data: bytes):
    pos = 0
    while pos < len(data):
        key, pos = _read_varint(data, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _read_varint(data, pos)
        elif wire == 1:
            value, pos = data[pos:pos + 8], pos + 8
        elif wire == 2:
            length, pos = _read_varint(data, pos)
            value, pos = data[pos:pos + length], pos + length
        elif wire == 5:
            value, pos = data[pos:pos + 4], pos + 4
        else:
            raise ValueError(f'unsupported protobuf wire type {wire}')
        yield number, wire, value


def _packed(data: bytes) -> list[int]:
    out, pos = [], 0
    while pos < len(data):
        value, pos = _read_varint(data, pos)
        out.append(value)
    return out


def _value(data: bytes) -> Any:
    for number, _, value in _fields(data):
        if number == 1:
            return value.decode('utf-8')
        if number == 2:
            return struct.unpack('<f', value)[0]
        if number == 3:
            return struct.unpack('<d', value)[0]
        if number in (4, 5):
            return value if number == 5 or value < 2 ** 63 else value - 2 ** 64
        if number == 6:
            return (value >> 1) ^ -(value & 1)
        if number == 7:
            return bool(value)
    return None


def _rings(commands: list[int]) -> list[list[tuple[int, int]]]:
    rings: list[list[tuple[int, int]]] = []
    x = y = 0
    i = 0
    while i < len(commands):
        command, count = commands[i] & 7, commands[i] >> 3
        i += 1
        if command in (1, 2):
            for _ in range(count):
                dx, dy = commands[i], commands[i + 1]
                i += 2
                x += (dx >> 1) ^ -(dx & 1)
                y += (dy >> 1) ^ -(dy & 1)
                if command == 1:
                    rings.append([])
                rings[-1].append((x, y))
        elif command != 7:
            raise ValueError(f'unknown MVT geometry command {command}')
    return rings


def decode_mvt(data: bytes) -> dict[str, dict[str, Any]]:
    """Decode a vector tile into {layer: {'extent', 'features': [{id, type, properties, rings}]}}."""
    layers: dict[str, dict[str, Any]] = {}
    for number, _, layer_bytes in _fields(data):
        if number != 3:
            continue
        name, extent, keys, values, raw_features = '', 4096, [], [], []
        for field, _, value in _fields(layer_bytes):
            if field == 1:
                name = value.decode('utf-8')
            elif field == 2:
                raw_features.append(value)
            elif field == 3:
                keys.append(value.decode('utf-8'))
            elif field == 4:
                values.append(_value(value))
            elif field == 5:
                extent = value
        features = []
        for raw in raw_features:
            feature: dict[str, Any] = {'id': None, 'type': 0, 'properties': {}, 'rings': []}
            for field, _, value in _fields(raw):
                if field == 1:
                    feature['id'] = value
                elif field == 2:
                    tags = _packed(value)
                    feature['properties'] = {keys[tags[j]]: values[tags[j + 1]] for j in range(0, len(tags) - 1, 2)}
                elif field == 3:
                    feature['type'] = value
                elif field == 4:
                    feature['rings'] = _rings(_packed(value))
            features.append(feature)
        layers[name] = {'extent': extent, 'features': features}
    return layers


# --- tile geometry ---------------------------------------------------------------------------

def tile_bbox(z: int, x: int, y: int) -> list[float]:
    n = 2 ** z

    def lat(ty: float) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n))))

    return [x / n * 360 - 180, lat(y + 1), (x + 1) / n * 360 - 180, lat(y)]


def _fractional_tile(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    phi = math.radians(lat)
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(phi)) / math.pi) / 2 * n


def tiles_for_bbox(bbox: list[float], z: int) -> list[tuple[int, int]]:
    west, south, east, north = bbox
    x0, y0 = _fractional_tile(west, north, z)
    x1, y1 = _fractional_tile(east, south, z)
    return [(x, y) for y in range(math.floor(y0), math.floor(y1) + 1) for x in range(math.floor(x0), math.floor(x1) + 1)]


def _signed_area(ring: list[tuple[float, float]]) -> float:
    return sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) / 2


def feature_polygons_lonlat(feature: dict[str, Any], z: int, x: int, y: int, extent: int) -> list[list[list[list[float]]]]:
    """Group MVT rings into polygons (exterior rings have positive area in tile space) in lon/lat."""
    n = 2 ** z
    polygons: list[list[list[list[float]]]] = []
    for ring in feature['rings']:
        if len(ring) < 3:
            continue
        area = _signed_area(ring)
        if area == 0:
            continue
        coords = []
        for px, py in ring + [ring[0]]:
            lon = (x + px / extent) / n * 360 - 180
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / extent) / n))))
            coords.append([lon, lat])
        if area > 0:
            polygons.append([coords])
        elif polygons:
            polygons[-1].append(coords)
    return polygons


def _cached(cache_dir: Path, relative: str, url: str, fetch: Fetch) -> bytes | None:
    """Read a tile from the cache, fetching it once. An empty file records 'no tile here'."""
    path = cache_dir / relative
    if path.exists():
        data = path.read_bytes()
        return data or None
    data = fetch(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    tmp.write_bytes(data or b'')
    tmp.replace(path)
    return data


def prefetch_tiles(bbox: list[float], cache_dir: Path, *, zoom: int = 16, dem_zoom: int = 14, fetch: Fetch | None = None) -> dict[str, int]:
    """Download every footprint and DEM tile for bbox into the cache; returns tile counts."""
    fetch = fetch or default_fetch
    footprint = tiles_for_bbox(bbox, zoom)
    for x, y in footprint:
        _cached(cache_dir, f'bvmap/{zoom}/{x}/{y}.pbf', BVMAP_URL.format(z=zoom, x=x, y=y), fetch)
    dem = _dem_tiles(bbox, dem_zoom)
    for x, y in dem:
        _cached(cache_dir, f'dem/{dem_zoom}/{x}/{y}.png', DEM_URL.format(z=dem_zoom, x=x, y=y), fetch)
    return {'footprint_tiles': len(footprint), 'dem_tiles': len(dem)}


def fetch_gsi_buildings(
    bbox: list[float], cache_dir: Path, *, zoom: int = 16, fetch: Fetch | None = None, layer: str = 'BldA',
) -> list[dict[str, Any]]:
    """Return GeoJSON-like building features intersecting bbox, with seam pieces joined."""
    from shapely.geometry import Polygon, box, mapping
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union
    from shapely import make_valid, set_precision

    fetch = fetch or default_fetch
    whole: list[tuple[Any, dict[str, Any]]] = []
    seam: dict[Any, list[Any]] = {}
    for x, y in tiles_for_bbox(bbox, zoom):
        data = _cached(cache_dir, f'bvmap/{zoom}/{x}/{y}.pbf', BVMAP_URL.format(z=zoom, x=x, y=y), fetch)
        if not data:
            continue
        decoded = decode_mvt(data).get(layer)
        if not decoded:
            continue
        extent = decoded['extent']
        west, south, east, north = tile_bbox(zoom, x, y)
        eps_x, eps_y = (east - west) / extent, (north - south) / extent
        for feature in decoded['features']:
            if feature['type'] != 3:
                continue
            props = {k: v for k, v in feature['properties'].items()}
            code = props.get('vt_code', props.get('ftCode'))
            for rings in feature_polygons_lonlat(feature, zoom, x, y, extent):
                polygon = make_valid(Polygon(rings[0], rings[1:]))
                parts = [polygon] if polygon.geom_type == 'Polygon' else [g for g in getattr(polygon, 'geoms', []) if g.geom_type == 'Polygon']
                for part in parts:
                    if part.is_empty or part.area <= 0:
                        continue
                    minx, miny, maxx, maxy = part.bounds
                    on_edge = minx <= west + eps_x or maxx >= east - eps_x or miny <= south + eps_y or maxy >= north - eps_y
                    if on_edge:
                        seam.setdefault(code, []).append(part)
                    else:
                        whole.append((part, {'vt_code': code}))
    for code, parts in seam.items():
        merged = unary_union(parts)
        for part in (merged.geoms if hasattr(merged, 'geoms') else [merged]):
            if part.geom_type == 'Polygon' and part.area > 0:
                whole.append((part, {'vt_code': code}))
    area = box(*bbox)
    features = []
    seen: set[str] = set()
    for polygon, props in whole:
        if not polygon.intersects(area):
            continue
        polygon = orient(set_precision(polygon, 1e-8), 1.0)
        if polygon.is_empty or polygon.geom_type != 'Polygon':
            continue
        identifier = 'gsi/' + hashlib.sha1(polygon.wkb).hexdigest()[:16]
        if identifier in seen:
            continue
        seen.add(identifier)
        geometry = mapping(polygon)
        features.append({
            'type': 'Feature',
            'id': identifier,
            'properties': {**props, 'source': 'gsi-optimal-bvmap'},
            'geometry': {'type': 'Polygon', 'coordinates': [[list(p) for p in ring] for ring in geometry['coordinates']]},
        })
    features.sort(key=lambda f: f['id'])
    return features


def orthophoto_texture(bbox: list[float], cache_dir: Path, *, zoom: int = 18, fetch: Fetch | None = None):
    """Mosaic the GSI seamless photo over bbox from cached tiles; returns (PIL image, [w, s, e, n])."""
    from PIL import Image

    fetch = fetch or default_fetch
    tiles = tiles_for_bbox(bbox, zoom)
    xs = sorted({x for x, _ in tiles})
    ys = sorted({y for _, y in tiles})
    canvas = Image.new('RGB', (len(xs) * 256, len(ys) * 256))
    for x, y in tiles:
        data = _cached(cache_dir, f'photo/{zoom}/{x}/{y}.jpg', PHOTO_URL.format(z=zoom, x=x, y=y), fetch)
        if data:
            canvas.paste(Image.open(io.BytesIO(data)).convert('RGB'), ((x - xs[0]) * 256, (y - ys[0]) * 256))
    west, _, _, north = tile_bbox(zoom, xs[0], ys[0])
    _, south, east, _ = tile_bbox(zoom, xs[-1], ys[-1])
    return canvas, [west, south, east, north]


# --- ground heights ---------------------------------------------------------------------------

def _dem_tiles(bbox: list[float], z: int) -> list[tuple[int, int]]:
    tiles = tiles_for_bbox(bbox, z)
    xs = [x for x, _ in tiles]
    ys = [y for _, y in tiles]
    return [(x, y) for y in range(min(ys) - 1, max(ys) + 2) for x in range(min(xs) - 1, max(xs) + 2)]


def _decode_dem_png(data: bytes | None):
    import numpy as np
    from PIL import Image

    if not data:
        return np.zeros((256, 256), dtype=np.float32)
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert('RGB'), dtype=np.int64)
    raw = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    raw = np.where(raw >= 2 ** 23, raw - 2 ** 24, raw)
    heights = raw.astype(np.float32) * 0.01
    heights[raw == -(2 ** 23)] = 0.0  # 0x800000 is nodata
    return heights


def dem_sampler(bbox: list[float], cache_dir: Path, *, zoom: int = 14, fetch: Fetch | None = None) -> Callable[[float, float], float]:
    """Return f(lon, lat) -> orthometric height in meters, bilinear between GSI DEM pixel centers."""
    import numpy as np

    fetch = fetch or default_fetch
    tiles = _dem_tiles(bbox, zoom)
    x0 = min(x for x, _ in tiles)
    y0 = min(y for _, y in tiles)
    width = (max(x for x, _ in tiles) - x0 + 1) * 256
    height = (max(y for _, y in tiles) - y0 + 1) * 256
    grid = np.zeros((height, width), dtype=np.float32)
    for x, y in tiles:
        data = _cached(cache_dir, f'dem/{zoom}/{x}/{y}.png', DEM_URL.format(z=zoom, x=x, y=y), fetch)
        grid[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256] = _decode_dem_png(data)

    def sample(lon: float, lat: float) -> float:
        fx, fy = _fractional_tile(lon, lat, zoom)
        px = (fx - x0) * 256 - 0.5
        py = (fy - y0) * 256 - 0.5
        ix = min(max(int(math.floor(px)), 0), width - 2)
        iy = min(max(int(math.floor(py)), 0), height - 2)
        tx = min(max(px - ix, 0.0), 1.0)
        ty = min(max(py - iy, 0.0), 1.0)
        top = grid[iy, ix] * (1 - tx) + grid[iy, ix + 1] * tx
        bottom = grid[iy + 1, ix] * (1 - tx) + grid[iy + 1, ix + 1] * tx
        return float(top * (1 - ty) + bottom * ty)

    return sample
