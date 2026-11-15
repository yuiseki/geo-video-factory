"""Collect small, georeferenced 2x2 GSI tile samples for the episode research."""
from __future__ import annotations

import io
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent
ZOOM = 16
TILES = {
    "std": ("標準地図", "png"),
    "pale": ("淡色地図", "png"),
    "ort_1928": ("1928年頃", "png"),
    "ort_riku10": ("1936年〜1942年頃", "png"),
    "ort_USA10": ("1945年〜1950年", "png"),
    "ort_old10": ("1961年〜1969年", "png"),
    "gazo1": ("1974年〜1978年", "jpg"),
    "gazo2": ("1979年〜1983年", "jpg"),
    "gazo3": ("1984年〜1986年", "jpg"),
    "gazo4": ("1987年〜1990年", "jpg"),
    "seamlessphoto": ("全国最新写真（複数時期の合成）", "jpg"),
}
PLACES = {
    "dotonbori": {"name": "道頓堀・戎橋周辺", "center": [135.50115, 34.66881],
        "layers": ["ort_1928", "ort_riku10", "ort_USA10", "ort_old10", "gazo1", "gazo4", "seamlessphoto", "std", "pale"]},
    "yanagibashi": {"name": "柳橋・両国橋周辺", "center": [139.78746, 35.69521],
        "layers": ["ort_riku10", "ort_USA10", "ort_old10", "gazo1", "gazo4", "seamlessphoto", "std", "pale"]},
    "shimbashi": {"name": "新橋跡・汐留川周辺", "center": [139.7617, 35.6666],
        "layers": ["ort_riku10", "ort_USA10", "ort_old10", "gazo1", "gazo4", "seamlessphoto", "std", "pale"]},
    "cosmosquare": {"name": "コスモスクエア駅北方の沖合（参考）", "center": [135.41238, 34.64713],
        "layers": ["ort_USA10", "ort_old10", "gazo1", "gazo2", "gazo3", "gazo4", "seamlessphoto"]},
    "cosmosquare_station": {"name": "コスモスクエア駅・咲洲周辺", "center": [135.4125, 34.6427],
        "layers": ["ort_USA10", "ort_old10", "gazo1", "gazo2", "gazo3", "gazo4", "seamlessphoto", "std", "pale"]},
}


def fractional_tile(lon, lat):
    n = 2 ** ZOOM
    return ((lon + 180) / 360 * n,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def bounds(x, y):
    n = 2 ** ZOOM
    lon = lambda a: a / n * 360 - 180
    lat = lambda a: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * a / n))))
    return [lon(x), lat(y + 2), lon(x + 2), lat(y)]


def main():
    session = requests.Session()
    session.headers["User-Agent"] = "YuisekinTV map research/1.0 (small manual selection)"
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "zoom": ZOOM,
        "attribution": "出典：国土地理院（地理院タイル）を加工 https://maps.gsi.go.jp/development/ichiran.html",
        "notes": ["年代はタイル提供元の範囲。個別の撮影日は未確認。", "透明部は画像の欠落または範囲外。海や埋立前を意味するとは限らない。", "gazo1〜4はRGB各値3以下の画素を欠損として透明化。元タイルはrawに保存。", "旧写真と現代地図の位置にはずれがあり得る。"], "places": {}}
    only = os.environ.get("GSI_PLACE")
    layers_only = set(filter(None, os.environ.get("GSI_ONLY_LAYERS", "").split(",")))
    if (only or layers_only) and (ROOT / "manifest.json").exists():
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        manifest["places"]["cosmosquare"]["name"] = PLACES["cosmosquare"]["name"]
    for place_id, place in PLACES.items():
        if only and place_id != only:
            continue
        xf, yf = fractional_tile(*place["center"])
        x0, y0 = math.floor(xf - 0.5), math.floor(yf - 0.5)
        dest = ROOT / place_id
        dest.mkdir(parents=True, exist_ok=True)
        record = manifest["places"].get(place_id, {"name": place["name"], "center_lon_lat": place["center"],
            "bbox_west_south_east_north": bounds(x0, y0), "layers": {}})
        for layer_id in place["layers"]:
            if layers_only and layer_id not in layers_only:
                continue
            period, ext = TILES[layer_id]
            canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            tile_results = []
            for dy in range(2):
                for dx in range(2):
                    x, y = x0 + dx, y0 + dy
                    url = f"https://cyberjapandata.gsi.go.jp/xyz/{layer_id}/{ZOOM}/{x}/{y}.{ext}"
                    item = {"url": url}
                    try:
                        response = session.get(url, timeout=25)
                        item["http_status"] = response.status_code
                        if response.ok:
                            tile = Image.open(io.BytesIO(response.content)).convert("RGBA")
                            if tile.size != (256, 256):
                                raise ValueError(f"unexpected tile size {tile.size}")
                            raw = dest / "raw" / layer_id / str(ZOOM) / str(x) / f"{y}.{ext}"
                            raw.parent.mkdir(parents=True, exist_ok=True)
                            raw.write_bytes(response.content)
                            item["raw_file"] = str(raw.relative_to(ROOT))
                            if layer_id.startswith("gazo"):
                                pix = tile.load()
                                for py in range(256):
                                    for px in range(256):
                                        r, g, b, a = pix[px, py]
                                        if max(r, g, b) <= 3:
                                            pix[px, py] = (r, g, b, 0)
                            canvas.paste(tile, (dx * 256, dy * 256))
                    except (requests.RequestException, OSError, ValueError) as exc:
                        item["error"] = str(exc)
                    tile_results.append(item)
                    time.sleep(0.2)
            alpha = canvas.getchannel("A")
            total = canvas.width * canvas.height
            visible = total - alpha.histogram()[0]
            target_xy = (int((xf - x0) * 256), int((yf - y0) * 256))
            name = f"{layer_id}.png"
            if visible:
                canvas.save(dest / name, optimize=True)
            record["layers"][layer_id] = {"period": period, "mosaic_file": f"{place_id}/{name}" if visible else None,
                "visible_fraction": round(visible / total, 4), "target_pixel_has_image": bool(alpha.getpixel(target_xy)),
                "tiles": tile_results}
            print(f"{place_id:14} {layer_id:14} image={visible / total:.1%} center={bool(alpha.getpixel(target_xy))}", flush=True)
        manifest["places"][place_id] = record
        (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
