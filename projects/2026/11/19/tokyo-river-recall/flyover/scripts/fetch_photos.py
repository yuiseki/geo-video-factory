#!/usr/bin/env python3
"""Download commercial-use-safe (CC0/PD/CC-BY) Wikimedia Commons photos and record credits."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
OUT_IMG_DIR = PROJECT_DIR / "flyover" / "assets" / "photos"
CREDITS_PATH = PROJECT_DIR / "research" / "photo_credits.json"

TARGETS = [
    ("shibuya_stream_river.jpg", "File:Shibuya River, near Shibuya Stream.jpg", "渋谷川（渋谷ストリーム付近・開渠部）"),
    ("shibuya_cat_street.jpg", "File:Cat Street Tokyo 2.JPG", "旧渋谷川（キャットストリート・暗渠上の遊歩道）"),
    ("kitazawa_greenway_daizawa.jpg", "File:Kitazawa River, Daizawa 3-chōme.jpg", "北沢川緑道（世田谷区代沢）"),
    ("karasuyama_greenway.jpg", "File:烏山川緑道.jpg", "烏山川緑道（世田谷区）"),
    ("tokyo_expressway_higashi_ginza.jpg", "File:Tokyo Expressway Higashi Ginza Exit 1.jpg", "東京高速道路（KK線・東銀座付近）"),
    ("tsukiji_river_park.jpg", "File:入船橋から見た築地川公園.jpg", "築地川公園（入船橋から望む旧築地川跡）"),
    ("hamachogawa_greenway.jpg", "File:浜町川緑道(弁慶像).jpg", "浜町川緑道（中央区日本橋浜町）"),
    ("tamagawa_josui_greenway.jpg", "File:玉川上水第二緑道.jpg", "玉川上水第二緑道（旧玉川上水）"),
    ("sanyabori_ukiyoe.jpg", "File:NDL1312270 名所江戸百景 真乳山山谷堀夜景.jpg", "名所江戸百景「真乳山山谷堀夜景」（江戸時代の山谷堀）"),
]


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text or "")).strip()


def main() -> None:
    OUT_IMG_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    headers = {"User-Agent": "GeoVideoFactoryBot/1.0 (https://github.com/geolonia/geo-video-factory; contact@geolonia.com)"}

    for idx, (local_name, wiki_title, desc_ja) in enumerate(TARGETS):
        if idx > 0:
            time.sleep(2.5)
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query",
            "titles": wiki_title,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": "1200",
            "format": "json",
        })
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        ii = (page.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
        artist = strip_html(meta.get("Artist", {}).get("value", "")) or "不明"
        img_url = ii.get("thumburl") or ii.get("url")
        page_url = ii.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(wiki_title)}"

        if not img_url:
            print(f"[SKIP] {wiki_title}: no image URL")
            continue
        if "SA" in lic or "NC" in lic:
            print(f"[SKIP] {wiki_title}: license {lic} excluded")
            continue

        dest = OUT_IMG_DIR / local_name
        if not dest.exists() or dest.stat().st_size == 0:
            time.sleep(2.5)
            for attempt in range(3):
                try:
                    img_req = urllib.request.Request(img_url, headers=headers)
                    with urllib.request.urlopen(img_req, timeout=30) as ir:
                        dest.write_bytes(ir.read())
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 429 and attempt < 2:
                        time.sleep(5.0 * (attempt + 1))
                        continue
                    raise

        credit = f"写真：{artist} / Wikimedia Commons（{lic}）" if "Public domain" not in lic else f"図版：{artist} / Wikimedia Commons（Public domain）"
        records.append({
            "file": f"assets/photos/{local_name}",
            "subject": desc_ja,
            "wiki_title": wiki_title,
            "page_url": page_url,
            "image_url": img_url,
            "artist": artist,
            "license": lic,
            "commercial_use": True,
            "credit_text": credit,
        })
        print(f"[OK] {local_name} ({lic}) - {artist}")

    CREDITS_PATH.write_text(json.dumps({"fetched_at": "2026-11-19", "photos": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(records)} photo credits to {CREDITS_PATH}")


if __name__ == "__main__":
    main()
