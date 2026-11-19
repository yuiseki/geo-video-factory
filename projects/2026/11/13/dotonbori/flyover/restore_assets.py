#!/usr/bin/env python3
"""Restore gitignored photo, map, and Gyazo assets for dotonbori from manifests and credits."""
from __future__ import annotations

import io
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

from PIL import Image

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
UA = "geo-video-factory/1.0 (https://github.com/geolonia/geo-video-factory)"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def restore_commons() -> None:
    credits_data = json.loads((ASSETS / "commons/credits.json").read_text(encoding="utf-8"))
    for key, info in credits_data.items():
        dst = ASSETS / "commons" / f"{key}.jpg"
        if dst.exists() and dst.stat().st_size > 0:
            continue
        url = info["source_url"]
        print(f"Downloading {dst.relative_to(ROOT)} ...", flush=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(fetch(url))


def restore_commons_v013() -> None:
    credits_data = json.loads((ASSETS / "commons-v013/credits.json").read_text(encoding="utf-8"))
    for item in credits_data:
        dst = ROOT / item["file"]
        if dst.exists() and dst.stat().st_size > 0:
            continue
        title = item["title"]
        api = (
            "https://commons.wikimedia.org/w/api.php?action=query&format=json"
            "&prop=imageinfo&iiprop=url&iiurlwidth=1920&titles="
            + urllib.parse.quote(title)
        )
        data = json.loads(fetch(api).decode("utf-8"))
        pages = data["query"]["pages"]
        page = next(iter(pages.values()))
        ii = page["imageinfo"][0]
        url = ii.get("thumburl") or ii["url"]
        print(f"Downloading {dst.relative_to(ROOT)} ...", flush=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(fetch(url))

    kukuru = ASSETS / "commons-v013/kukuru-honten.webp"
    if not kukuru.exists() or kukuru.stat().st_size == 0:
        img_url = "https://dotonbori-kukuru.com/wp-content/uploads/2024/02/Honten-1.jpg"
        print(f"Downloading {kukuru.relative_to(ROOT)} from {img_url} ...", flush=True)
        raw = fetch(img_url)
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.save(kukuru, "WEBP", quality=90)


def restore_gyazo() -> None:
    spec = json.loads((ROOT / "shots/dotonbori.v0.1.7.json").read_text(encoding="utf-8"))
    gyazo_srcs = sorted({
        ov["src"]
        for shot in spec["shots"]
        for ov in shot.get("overlays", [])
        if ov.get("src", "").startswith("assets/gyazo/")
    })
    for src in gyazo_srcs:
        dst = ROOT / src
        if dst.exists() and dst.stat().st_size > 0:
            continue
        img_id = dst.stem
        url = f"https://i.gyazo.com/{img_id}.jpg"
        print(f"Downloading {src} ...", flush=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(fetch(url))


def restore_maps() -> None:
    spec = json.loads((ROOT / "shots/dotonbori.v0.1.7.json").read_text(encoding="utf-8"))
    needed = sorted({
        ov["src"]
        for shot in spec["shots"]
        for ov in shot.get("overlays", [])
        if ov.get("src", "").startswith("assets/maps/")
    })
    manifest = json.loads((ASSETS / "maps/manifest.json").read_text(encoding="utf-8"))
    by_mosaic = {}
    for place in manifest["places"].values():
        for layer_name, layer in place["layers"].items():
            if isinstance(layer, dict) and layer.get("mosaic_file"):
                by_mosaic[f"assets/maps/{layer['mosaic_file']}"] = (layer_name, layer)

    for src in needed:
        dst = ROOT / src
        if dst.exists() and dst.stat().st_size > 0:
            continue
        layer_name, layer = by_mosaic[src]
        tiles = layer["tiles"]
        print(f"Building {src} ({len(tiles)} tiles) ...", flush=True)
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        for idx, tile in enumerate(tiles):
            raw = fetch(tile["url"])
            im = Image.open(io.BytesIO(raw)).convert("RGBA")
            if layer_name.startswith("gazo"):
                px = im.load()
                w, h = im.size
                for y in range(h):
                    for x in range(w):
                        r, g, b, a = px[x, y]
                        if r <= 3 and g <= 3 and b <= 3:
                            px[x, y] = (r, g, b, 0)
            col = idx % 2
            row = idx // 2
            canvas.paste(im, (col * 256, row * 256))
        dst.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(dst, "PNG")


def main() -> None:
    restore_commons()
    restore_commons_v013()
    restore_gyazo()
    restore_maps()
    print("All assets restored.")


if __name__ == "__main__":
    main()
