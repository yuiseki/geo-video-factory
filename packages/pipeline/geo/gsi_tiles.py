"""Collect georeferenced GSI tile mosaics (current & historical aerial photos) for a project."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from PIL import Image

GSI_TILES: dict[str, tuple[str, str]] = {
    'std': ('標準地図', 'png'),
    'pale': ('淡色地図', 'png'),
    'ort_1928': ('1928年頃', 'png'),
    'ort_riku10': ('1936年〜1942年頃', 'png'),
    'ort_USA10': ('1945年〜1950年', 'png'),
    'ort_old10': ('1961年〜1969年', 'png'),
    'gazo1': ('1974年〜1978年', 'jpg'),
    'gazo2': ('1979年〜1983年', 'jpg'),
    'gazo3': ('1984年〜1986年', 'jpg'),
    'gazo4': ('1987年〜1990年', 'jpg'),
    'seamlessphoto': ('全国最新写真（複数時期の合成）', 'jpg'),
}

ATTRIBUTION = '出典：国土地理院（地理院タイル）を加工 https://maps.gsi.go.jp/development/ichiran.html'
USER_AGENT = 'geo-video-factory gsi_tiles/1.0'


def fractional_tile(lon: float, lat: float, zoom: int = 16) -> tuple[float, float]:
    """Return fractional Web Mercator XYZ tile coordinates for (lon, lat) at zoom."""
    n = 2 ** zoom
    return (
        (lon + 180.0) / 360.0 * n,
        (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n,
    )


def tile_bounds(x0: int, y0: int, width_tiles: int = 2, height_tiles: int = 2, zoom: int = 16) -> list[float]:
    """Return [west, south, east, north] bounds for a tile grid starting at (x0, y0)."""
    n = 2 ** zoom
    lon = lambda a: a / n * 360.0 - 180.0
    lat = lambda a: math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * a / n))))
    return [lon(x0), lat(y0 + height_tiles), lon(x0 + width_tiles), lat(y0)]


def mask_dark_nodata(tile: Image.Image, threshold: int = 3) -> Image.Image:
    """Turn near-black pixels (e.g. gazo1-4 missing margins) transparent."""
    out = tile.convert('RGBA')
    pix = out.load()
    w, h = out.size
    for py in range(h):
        for px in range(w):
            r, g, b, _ = pix[px, py]
            if max(r, g, b) <= threshold:
                pix[px, py] = (r, g, b, 0)
    return out


def stitch_mosaic(
    tiles: dict[tuple[int, int], Image.Image],
    x0: int,
    y0: int,
    width_tiles: int = 2,
    height_tiles: int = 2,
) -> tuple[Image.Image, int, int]:
    """Stitch 256x256 tiles into a single RGBA mosaic and return (image, visible_px, total_px)."""
    canvas = Image.new('RGBA', (width_tiles * 256, height_tiles * 256), (0, 0, 0, 0))
    for dy in range(height_tiles):
        for dx in range(width_tiles):
            tile = tiles.get((x0 + dx, y0 + dy))
            if tile is not None:
                canvas.paste(tile.convert('RGBA'), (dx * 256, dy * 256))
    alpha = canvas.getchannel('A')
    total = canvas.width * canvas.height
    visible = total - alpha.histogram()[0]
    return canvas, visible, total


def _default_fetcher(url: str) -> tuple[int, bytes]:
    req = Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urlopen(req, timeout=25) as resp:
            return resp.status, resp.read()
    except HTTPError as exc:
        return exc.code, b''


def collect_places(
    places: dict,
    out_dir: Path,
    *,
    zoom: int = 16,
    width_tiles: int = 2,
    height_tiles: int = 2,
    only_place: str | None = None,
    only_layers: set[str] | None = None,
    delay: float = 0.2,
    fetcher: Callable[[str], tuple[int, bytes]] | None = None,
) -> dict:
    """Download and stitch GSI tiles for each place and write manifest.json."""
    fetch = fetcher or _default_fetcher
    manifest_path = out_dir / 'manifest.json'
    if (only_place or only_layers) and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    else:
        manifest = {
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'zoom': zoom,
            'attribution': ATTRIBUTION,
            'notes': [
                '年代はタイル提供元の範囲。個別の撮影日は未確認。',
                '透明部は画像の欠落または範囲外。海や埋立前を意味するとは限らない。',
                'gazo1〜4はRGB各値3以下の画素を欠損として透明化。元タイルはrawに保存。',
                '旧写真と現代地図の位置にはずれがあり得る。',
            ],
            'places': {},
        }

    for place_id, place in places.items():
        if only_place and place_id != only_place:
            continue
        xf, yf = fractional_tile(*place['center'], zoom=zoom)
        x0 = math.floor(xf - (width_tiles - 1) / 2)
        y0 = math.floor(yf - (height_tiles - 1) / 2)
        dest = out_dir / place_id
        dest.mkdir(parents=True, exist_ok=True)
        record = manifest['places'].get(
            place_id,
            {
                'name': place.get('name', place_id),
                'center_lon_lat': place['center'],
                'bbox_west_south_east_north': tile_bounds(x0, y0, width_tiles, height_tiles, zoom=zoom),
                'layers': {},
            },
        )
        for layer_id in place['layers']:
            if only_layers and layer_id not in only_layers:
                continue
            period, ext = GSI_TILES[layer_id]
            tiles: dict[tuple[int, int], Image.Image] = {}
            tile_results = []
            for dy in range(height_tiles):
                for dx in range(width_tiles):
                    x, y = x0 + dx, y0 + dy
                    url = f'https://cyberjapandata.gsi.go.jp/xyz/{layer_id}/{zoom}/{x}/{y}.{ext}'
                    item: dict[str, object] = {'url': url}
                    try:
                        status, content = fetch(url)
                        item['http_status'] = status
                        if 200 <= status < 300:
                            tile = Image.open(io.BytesIO(content)).convert('RGBA')
                            if tile.size != (256, 256):
                                raise ValueError(f'unexpected tile size {tile.size}')
                            raw = dest / 'raw' / layer_id / str(zoom) / str(x) / f'{y}.{ext}'
                            raw.parent.mkdir(parents=True, exist_ok=True)
                            raw.write_bytes(content)
                            item['raw_file'] = str(raw.relative_to(out_dir))
                            if layer_id.startswith('gazo'):
                                tile = mask_dark_nodata(tile)
                            tiles[(x, y)] = tile
                    except (URLError, OSError, ValueError) as exc:
                        item['error'] = str(exc)
                    tile_results.append(item)
                    if delay > 0:
                        time.sleep(delay)

            canvas, visible, total = stitch_mosaic(tiles, x0, y0, width_tiles, height_tiles)
            alpha = canvas.getchannel('A')
            target_xy = (
                min(canvas.width - 1, max(0, int((xf - x0) * 256))),
                min(canvas.height - 1, max(0, int((yf - y0) * 256))),
            )
            name = f'{layer_id}.png'
            if visible:
                canvas.save(dest / name, optimize=True)
            record['layers'][layer_id] = {
                'period': period,
                'mosaic_file': f'{place_id}/{name}' if visible else None,
                'visible_fraction': round(visible / total, 4),
                'target_pixel_has_image': bool(alpha.getpixel(target_xy)),
                'tiles': tile_results,
            }
        manifest['places'][place_id] = record
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('places_json', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--zoom', type=int, default=16)
    p.add_argument('--only', help='collect only this place_id')
    p.add_argument('--layers', help='comma-separated layer IDs to collect')
    p.add_argument('--delay', type=float, default=0.2)
    args = p.parse_args()
    places = json.loads(args.places_json.read_text(encoding='utf-8'))
    only_layers = set(filter(None, (args.layers or '').split(','))) or None
    collect_places(places, args.out, zoom=args.zoom, only_place=args.only, only_layers=only_layers, delay=args.delay)


if __name__ == '__main__':
    main()
