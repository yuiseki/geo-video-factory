"""Freeze the PLATEAU 3D Tiles visible in a scene into fixed, local GLB assets."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import math
from pathlib import Path
import struct
from typing import Any, Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from PIL import Image

USER_AGENT = 'geo-video-factory plateau_3d/1.0'
IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def region_intersects_bbox(region: list[float], bbox_degrees: list[float]) -> bool:
    """Test a 3D Tiles radian region against a [west, south, east, north] degree bbox."""
    if len(region) < 4 or len(bbox_degrees) != 4:
        raise ValueError('region and bbox must contain four coordinates')
    west, south, east, north = map(math.radians, bbox_degrees)
    rw, rs, re, rn = region[:4]
    lon_intersects = (rw <= east and re >= west) if west <= east else (rw <= east or re >= west)
    return lon_intersects and rs <= north and rn >= south


def _identity_transform(value: list[float]) -> bool:
    return len(value) == 16 and all(abs(a - b) < 1e-12 for a, b in zip(value, IDENTITY))


def iter_leaf_contents(tileset: dict[str, Any], bbox_degrees: list[float]):
    """Yield intersecting leaf contents, inheriting bounding regions down the tree.

    Parent contents are intentionally skipped when children exist. This freezes the
    most detailed available leaves and prevents parent/child overlap during playback.
    Non-identity transforms fail loudly until their full hierarchy is recorded.
    """
    def visit(tile: dict[str, Any], parent_region: list[float] | None, depth: int):
        transform = tile.get('transform')
        if transform is not None and not _identity_transform(transform):
            raise ValueError(f'unsupported 3D Tiles transform at depth {depth}')
        volume = tile.get('boundingVolume') or {}
        region = volume.get('region', parent_region)
        if region is not None and not region_intersects_bbox(region, bbox_degrees):
            return
        children = tile.get('children') or []
        if children:
            for child in children:
                yield from visit(child, region, depth + 1)
            return
        content = tile.get('content')
        if content:
            uri = content.get('uri') or content.get('url')
            if not uri:
                raise ValueError(f'3D Tiles content at depth {depth} has no uri')
            content_volume = content.get('boundingVolume') or {}
            content_region = content_volume.get('region', region)
            if content_region is None or region_intersects_bbox(content_region, bbox_degrees):
                yield {'uri': uri, 'region': content_region, 'depth': depth}

    root = tileset.get('root')
    if not isinstance(root, dict):
        raise ValueError('tileset is missing root tile')
    yield from visit(root, None, 0)


def _json_padded(data: bytes, label: str) -> dict[str, Any]:
    stripped = data.rstrip(b' \t\r\n\0')
    if not stripped:
        return {}
    try:
        value = json.loads(stripped)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'invalid {label} JSON in b3dm') from exc
    if not isinstance(value, dict):
        raise ValueError(f'{label} JSON in b3dm must be an object')
    return value


def parse_b3dm(payload: bytes) -> dict[str, Any]:
    """Return the embedded GLB and JSON feature/batch tables from a b3dm v1 tile."""
    if len(payload) < 28:
        raise ValueError('b3dm header is truncated')
    magic, version, byte_length, feature_json_len, feature_bin_len, batch_json_len, batch_bin_len = struct.unpack_from('<4sIIIIII', payload)
    if magic != b'b3dm' or version != 1:
        raise ValueError('unsupported b3dm magic or version')
    if byte_length != len(payload):
        raise ValueError(f'b3dm length mismatch: header {byte_length}, actual {len(payload)}')
    cursor = 28
    feature_end = cursor + feature_json_len
    feature_bin_end = feature_end + feature_bin_len
    batch_end = feature_bin_end + batch_json_len
    glb_start = batch_end + batch_bin_len
    if glb_start > byte_length:
        raise ValueError('b3dm table lengths exceed payload length')
    feature = _json_padded(payload[cursor:feature_end], 'feature table')
    batch = _json_padded(payload[feature_bin_end:batch_end], 'batch table')
    glb = payload[glb_start:]
    if len(glb) < 12 or glb[:4] != b'glTF':
        raise ValueError('b3dm payload does not contain an embedded GLB')
    return {'glb': glb, 'feature_table': feature, 'batch_table': batch}


def glb_chunks(payload: bytes) -> tuple[dict[str, Any], bytes, list[tuple[bytes, bytes]]]:
    """Read a GLB v2 JSON document and its chunks, preserving unknown chunks."""
    if len(payload) < 20 or payload[:4] != b'glTF':
        raise ValueError('payload is not a GLB')
    magic, version, total = struct.unpack_from('<4sII', payload)
    if version != 2 or total != len(payload):
        raise ValueError('unsupported GLB version or declared length')
    chunks: list[tuple[bytes, bytes]] = []
    cursor = 12
    while cursor < total:
        if cursor + 8 > total:
            raise ValueError('truncated GLB chunk header')
        length, kind = struct.unpack_from('<I4s', payload, cursor)
        cursor += 8
        end = cursor + length
        if end > total:
            raise ValueError('truncated GLB chunk payload')
        chunks.append((kind, payload[cursor:end]))
        cursor = end
    json_chunks = [data for kind, data in chunks if kind == b'JSON']
    if len(json_chunks) != 1:
        raise ValueError('GLB must contain exactly one JSON chunk')
    document = json.loads(json_chunks[0].rstrip(b' \t\r\n\0'))
    binary_chunks = [data for kind, data in chunks if kind == b'BIN\0']
    if len(binary_chunks) > 1:
        raise ValueError('GLB contains multiple BIN chunks')
    return document, binary_chunks[0] if binary_chunks else b'', chunks


def _buffer_view_bytes(document: dict[str, Any], binary: bytes, view_index: int) -> bytes:
    view = document['bufferViews'][view_index]
    start = int(view.get('byteOffset', 0))
    end = start + int(view['byteLength'])
    if start < 0 or end > len(binary):
        raise ValueError('GLB bufferView points outside the binary chunk')
    return binary[start:end]


def extract_gml_ids(payload: bytes, batch_table: dict[str, Any] | None = None) -> list[str]:
    """Extract legacy batch-table IDs or EXT_structural_metadata gml_id values."""
    batch_ids = (batch_table or {}).get('gml_id')
    if isinstance(batch_ids, list):
        return [str(value) for value in batch_ids]
    document, binary, _ = glb_chunks(payload)
    metadata = document.get('extensions', {}).get('EXT_structural_metadata', {})
    ids: list[str] = []
    for table in metadata.get('propertyTables', []):
        prop = table.get('properties', {}).get('gml_id')
        if not prop or 'values' not in prop or 'stringOffsets' not in prop:
            continue
        raw_values = _buffer_view_bytes(document, binary, prop['values'])
        raw_offsets = _buffer_view_bytes(document, binary, prop['stringOffsets'])
        offset_type = prop.get('stringOffsetType', 'UINT32')
        formats = {'UINT8': 'B', 'UINT16': 'H', 'UINT32': 'I'}
        code = formats.get(offset_type)
        if not code:
            raise ValueError(f'unsupported structural metadata string offset type: {offset_type}')
        width = struct.calcsize('<' + code)
        count = int(table['count'])
        if len(raw_offsets) < (count + 1) * width:
            raise ValueError('structural metadata string offsets are truncated')
        offsets = struct.unpack_from('<' + code * (count + 1), raw_offsets)
        if offsets[-1] > len(raw_values):
            raise ValueError('structural metadata string values are truncated')
        ids.extend(raw_values[offsets[i]:offsets[i + 1]].decode('utf-8') for i in range(count))
    return ids


def _resize_glb_textures(payload: bytes, max_dimension: int) -> bytes:
    document, binary, chunks = glb_chunks(payload)
    for image_spec in document.get('images', []):
        uri = image_spec.get('uri')
        if uri and not uri.startswith('data:'):
            raise ValueError(f'GLB references an external image that must be embedded before rendering: {uri}')
    if not binary or not document.get('images'):
        return payload
    mutable = bytearray(binary)
    for image_spec in document['images']:
        view_index = image_spec.get('bufferView')
        if view_index is None:
            continue
        original = _buffer_view_bytes(document, binary, view_index)
        try:
            image = Image.open(io.BytesIO(original))
            image.load()
        except (OSError, ValueError) as exc:
            raise ValueError(f'cannot decode embedded GLB image: {exc}') from exc
        if max(image.size) <= max_dimension:
            continue
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        encoded = io.BytesIO()
        image.save(encoded, 'WEBP', quality=88, method=4)
        image_spec['mimeType'] = 'image/webp'
        mutable.extend(b'\0' * ((-len(mutable)) % 4))
        view = document['bufferViews'][view_index]
        view['byteOffset'] = len(mutable)
        view['byteLength'] = len(encoded.getvalue())
        mutable.extend(encoded.getvalue())
    if len(mutable) == len(binary):
        return payload
    document.setdefault('buffers', [{}])[0]['byteLength'] = len(mutable)
    output_chunks: list[tuple[bytes, bytes]] = []
    for kind, data in chunks:
        if kind == b'JSON':
            data = json.dumps(document, separators=(',', ':')).encode('utf-8')
            data += b' ' * ((-len(data)) % 4)
        elif kind == b'BIN\0':
            data = bytes(mutable)
            data += b'\0' * ((-len(data)) % 4)
        output_chunks.append((kind, data))
    total = 12 + sum(8 + len(data) for _, data in output_chunks)
    return struct.pack('<4sII', b'glTF', 2, total) + b''.join(
        struct.pack('<I4s', len(data), kind) + data for kind, data in output_chunks
    )


def _default_fetch(url: str) -> bytes:
    request = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return response.read()


def prepare_tiles(
    tileset_url: str,
    bbox_degrees: list[float],
    output_dir: Path,
    *,
    max_texture_dimension: int = 2048,
    workers: int = 3,
    fetcher: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    """Download intersecting leaf models and write a fixed local manifest."""
    if max_texture_dimension <= 0 or workers <= 0:
        raise ValueError('max texture dimension and workers must be positive')
    fetch = fetcher or _default_fetch
    output_dir.mkdir(parents=True, exist_ok=True)
    models_dir = output_dir / 'models'
    models_dir.mkdir(parents=True, exist_ok=True)
    root = json.loads(fetch(tileset_url))

    def collect(tileset: dict[str, Any], base_url: str, inherited_depth: int = 0):
        for item in iter_leaf_contents(tileset, bbox_degrees):
            absolute = urljoin(base_url, item['uri'])
            if absolute.lower().endswith('.json'):
                yield from collect(json.loads(fetch(absolute)), absolute, item['depth'] + inherited_depth)
            else:
                yield {**item, 'uri': absolute, 'depth': item['depth'] + inherited_depth}

    selected = list(collect(root, tileset_url))
    if not selected:
        raise ValueError('no leaf content intersects the requested bbox')
    deduped = {item['uri']: item for item in selected}
    selected = sorted(deduped.values(), key=lambda item: item['uri'])

    def download(item: dict[str, Any]) -> dict[str, Any]:
        raw = fetch(item['uri'])
        if raw[:4] == b'b3dm':
            parsed = parse_b3dm(raw)
            glb = parsed['glb']
            ids = extract_gml_ids(glb, parsed['batch_table'])
            rtc = parsed['feature_table'].get('RTC_CENTER')
        elif raw[:4] == b'glTF':
            glb = raw
            ids = extract_gml_ids(glb)
            rtc = None
        else:
            raise ValueError(f'unsupported 3D Tiles content at {item["uri"]}: {raw[:4]!r}')
        document, _, _ = glb_chunks(glb)
        if rtc is None:
            rtc = document.get('extensions', {}).get('CESIUM_RTC', {}).get('center', [0, 0, 0])
        if len(rtc) != 3 or any(not isinstance(v, (int, float)) for v in rtc):
            raise ValueError(f'invalid RTC center in {item["uri"]}')
        source_hash = hashlib.sha256(item['uri'].encode()).hexdigest()[:20]
        model_path = models_dir / f'{source_hash}.glb'
        optimized = _resize_glb_textures(glb, max_texture_dimension)
        model_path.write_bytes(optimized)
        try:
            from building_appearance import extract_glb_feature_centroids
        except ImportError:
            from .building_appearance import extract_glb_feature_centroids
        rtc_floats = [float(v) for v in rtc]
        feature_centroids = extract_glb_feature_centroids(optimized, rtc_floats, ids) if ids else {}
        return {
            'source': item['uri'],
            'glb': model_path.relative_to(output_dir).as_posix(),
            'sha256': hashlib.sha256(optimized).hexdigest(),
            'source_sha256': hashlib.sha256(raw).hexdigest(),
            'source_bytes': len(raw),
            'bytes': len(optimized),
            'rtc': rtc_floats,
            'ids': ids,
            'feature_centroids': feature_centroids,
            'region': item['region'],
            'depth': item['depth'],
            'extensions': document.get('extensionsUsed', []),
        }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(download, item) for item in selected]
        for future in futures:
            results.append(future.result())
    results.sort(key=lambda item: item['source'])
    unique_ids = {identifier for item in results for identifier in item['ids']}
    manifest = {
        'format': 'geo-video-factory.plateau-3d/1',
        'tileset_url': tileset_url,
        'bbox_degrees': bbox_degrees,
        'center': [(bbox_degrees[0] + bbox_degrees[2]) / 2, (bbox_degrees[1] + bbox_degrees[3]) / 2],
        'tile_count': len(results),
        'tile_ids': len(unique_ids),
        'total_source_bytes': sum(item['source_bytes'] for item in results),
        'total_bytes': sum(item['bytes'] for item in results),
        'texture_max_dimension': max_texture_dimension,
        'tiles': results,
    }
    manifest_path = output_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tileset_url')
    parser.add_argument('--bbox', nargs=4, required=True, type=float, metavar=('WEST', 'SOUTH', 'EAST', 'NORTH'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-texture-dimension', type=int, default=2048)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--orthophoto', type=Path, help='local GSI orthophoto mosaic covering --bbox')
    parser.add_argument('--osm-geojson', type=Path, help='OSM building FeatureCollection to add as missing-building proxies')
    parser.add_argument('--citygml-geojson', type=Path, help='CityGML building footprints and heights as GeoJSON for PLATEAU models missing from the tiles')
    parser.add_argument('--seed', default='geo-video-factory', help='stable per-building appearance seed')
    args = parser.parse_args()
    manifest = prepare_tiles(args.tileset_url, args.bbox, args.out, max_texture_dimension=args.max_texture_dimension, workers=args.workers)
    if args.orthophoto:
        from building_appearance import apply_orthophoto_palette
        manifest = apply_orthophoto_palette(args.out, args.orthophoto, seed=args.seed)
    citygml_features = None
    if args.citygml_geojson:
        from building_appearance import apply_citygml_colors, build_osm_proxy_tiles
        citygml = json.loads(args.citygml_geojson.read_text(encoding='utf-8'))
        features = citygml.get('features') if isinstance(citygml, dict) else None
        if not isinstance(features, list):
            raise ValueError('--citygml-geojson must contain a GeoJSON FeatureCollection')
        citygml_features = features
        manifest = apply_citygml_colors(args.out, features)
        ortho = None
        if args.orthophoto:
            with Image.open(args.orthophoto) as source:
                ortho = source.convert('RGB')
        manifest = build_osm_proxy_tiles(features, args.bbox, args.out, kind='citygml-proxy', seed=args.seed, orthophoto=ortho)
    if args.osm_geojson:
        from building_appearance import build_osm_proxy_tiles
        geojson = json.loads(args.osm_geojson.read_text(encoding='utf-8'))
        features = geojson.get('features') if isinstance(geojson, dict) else None
        if not isinstance(features, list):
            raise ValueError('--osm-geojson must contain a GeoJSON FeatureCollection')
        ortho = None
        if args.orthophoto:
            with Image.open(args.orthophoto) as source:
                ortho = source.convert('RGB')
        plateau_ids = {str(identifier) for tile in manifest.get('tiles', []) for identifier in tile.get('ids', [])}
        manifest = build_osm_proxy_tiles(features, args.bbox, args.out, plateau_ids=plateau_ids, seed=args.seed, orthophoto=ortho, plateau_footprints=citygml_features)
    print(json.dumps({k: v for k, v in manifest.items() if k != 'tiles'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
