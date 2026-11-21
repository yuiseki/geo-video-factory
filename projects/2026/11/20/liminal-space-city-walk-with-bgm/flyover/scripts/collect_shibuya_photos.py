#!/usr/bin/env python3
"""Collect commercially usable, modifiable photos of Shibuya Crossing and Shibuya Center-gai
from Wikimedia Commons and Openverse.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request


USER_AGENT = "GeoVideoFactoryPhotoCollector/1.0 (https://github.com/yuiseki/geo-video-factory)"

ALLOWED_LICENSES_RE = re.compile(
    r"^(CC0|CC-Zero|Public domain|PDM|CC[ -]BY([ -]SA)?(\s+[0-9.]+)?(\s+\w+)?)$",
    re.IGNORECASE,
)
DISALLOWED_RE = re.compile(r"(NC|ND|NonCommercial|NoDerivatives|Copyrighted|Fair use)", re.IGNORECASE)


def is_modifiable_commercial_license(license_str: str) -> tuple[bool, bool]:
    """Return (allowed, is_share_alike)."""
    s = (license_str or "").strip()
    if not s or DISALLOWED_RE.search(s):
        return False, False
    low = s.lower()
    if "cc0" in low or "public domain" in low or low == "pdm":
        return True, False
    if "cc-by-sa" in low or "cc by-sa" in low or low == "by-sa":
        return True, True
    if "cc-by" in low or "cc by" in low or low == "by":
        return True, False
    return False, False


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(text or ""))).strip()


def fetch_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def query_commons_category(category: str, limit: int = 100) -> list[str]:
    titles: list[str] = []
    cmcontinue = None
    while len(titles) < limit:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmtype": "file",
            "cmlimit": str(min(50, limit - len(titles))),
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        data = fetch_json(url)
        for item in data.get("query", {}).get("categorymembers", []):
            titles.append(item["title"])
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    return titles


def query_commons_search(query: str, limit: int = 60) -> list[str]:
    titles: list[str] = []
    sroffset = 0
    while len(titles) < limit:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": "6",
            "srlimit": str(min(50, limit - len(titles))),
            "sroffset": str(sroffset),
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        data = fetch_json(url)
        batch = data.get("query", {}).get("search", [])
        if not batch:
            break
        for item in batch:
            titles.append(item["title"])
        if "continue" not in data:
            break
        sroffset = data["continue"].get("sroffset", sroffset + len(batch))
    return titles


def fetch_commons_imageinfo(titles: list[str], spot: str) -> list[dict]:
    records: list[dict] = []
    for i in range(0, len(titles), 25):
        chunk = titles[i : i + 25]
        params = {
            "action": "query",
            "titles": "|".join(chunk),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime|size",
            "iiurlwidth": "1600",
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        data = fetch_json(url)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            info = infos[0]
            mime = info.get("mime", "")
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                continue
            meta = info.get("extmetadata", {})
            lic = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
            allowed, share_alike = is_modifiable_commercial_license(lic)
            if not allowed:
                continue
            artist = strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown"
            desc = strip_html(meta.get("ImageDescription", {}).get("value", ""))
            download_url = info.get("thumburl") or info.get("url")
            orig_url = info.get("url")
            landing_url = info.get("descriptionurl")
            records.append(
                {
                    "spot": spot,
                    "source": "wikimedia_commons",
                    "title": page.get("title", ""),
                    "creator": artist,
                    "license": lic,
                    "share_alike": share_alike,
                    "description": desc[:240],
                    "download_url": download_url,
                    "original_url": orig_url,
                    "landing_url": landing_url,
                    "width": info.get("thumbwidth") or info.get("width"),
                    "height": info.get("thumbheight") or info.get("height"),
                }
            )
    return records


def query_openverse_images(query: str, spot: str, pages: int = 3) -> list[dict]:
    records: list[dict] = []
    for page in range(1, pages + 1):
        params = {
            "q": query,
            "license_type": "commercial,modification",
            "page_size": "20",
            "page": str(page),
        }
        url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"Openverse error ({query}, p{page}): {exc}")
            break
        results = data.get("results", [])
        if not results:
            break
        for r in results:
            lic_code = (r.get("license") or "").upper()
            lic_ver = r.get("license_version") or ""
            lic_str = f"CC {lic_code} {lic_ver}".strip() if lic_code not in ("CC0", "PDM") else lic_code
            allowed, share_alike = is_modifiable_commercial_license(lic_str)
            if not allowed:
                continue
            img_url = r.get("url")
            if not img_url:
                continue
            records.append(
                {
                    "spot": spot,
                    "source": f"openverse/{r.get('source', 'unknown')}",
                    "title": r.get("title") or r.get("id") or "untitled",
                    "creator": r.get("creator") or "Unknown",
                    "license": lic_str,
                    "share_alike": share_alike,
                    "description": "",
                    "download_url": img_url,
                    "original_url": img_url,
                    "landing_url": r.get("foreign_landing_url") or img_url,
                    "width": r.get("width"),
                    "height": r.get("height"),
                }
            )
        time.sleep(0.3)
    return records


def safe_filename(idx: int, title: str, url: str) -> str:
    ext = ".jpg"
    low_url = url.lower().split("?")[0]
    if low_url.endswith(".png"):
        ext = ".png"
    elif low_url.endswith(".webp"):
        ext = ".webp"
    stem = re.sub(r"^File:", "", title)
    stem = re.sub(r"\.[a-zA-Z0-9]+$", "", stem)
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_")[:60] or "photo"
    return f"{idx:03d}_{stem}{ext}"


def download_one(idx: int, rec: dict, base_dir: Path) -> dict:
    spot_dir = base_dir / rec["spot"]
    spot_dir.mkdir(parents=True, exist_ok=True)
    fname = safe_filename(idx, rec["title"], rec["download_url"])
    out_path = spot_dir / fname
    if out_path.exists() and out_path.stat().st_size > 1024:
        rec["local_path"] = str(out_path.relative_to(base_dir.parents[1]))
        rec["status"] = "cached"
        return rec
    try:
        req = urllib.request.Request(rec["download_url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=25) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "image" not in ctype and not rec["download_url"].lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                rec["status"] = f"skipped_content_type:{ctype}"
                return rec
            data = resp.read()
        if len(data) < 2048:
            rec["status"] = "skipped_too_small"
            return rec
        out_path.write_bytes(data)
        rec["local_path"] = str(out_path.relative_to(base_dir.parents[1]))
        rec["bytes"] = len(data)
        rec["status"] = "downloaded"
    except Exception as exc:
        rec["status"] = f"error:{exc}"
    return rec


def main() -> None:
    project_dir = Path(__file__).resolve().parents[2]
    photos_dir = project_dir / "flyover/assets/photos"
    manifest_path = project_dir / "research/photos_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    all_records: list[dict] = []

    # 1. Wikimedia Commons
    crossing_titles = list(
        dict.fromkeys(
            query_commons_category("Shibuya Crossing", 120)
            + query_commons_search('"Shibuya Crossing" OR "Shibuya Scramble"', 60)
        )
    )
    print(f"Commons Shibuya Crossing candidate titles: {len(crossing_titles)}")
    all_records.extend(fetch_commons_imageinfo(crossing_titles, "shibuya_crossing"))

    centergai_titles = list(
        dict.fromkeys(
            query_commons_category("Shibuya Center-gai", 80)
            + query_commons_search('"Shibuya Center-gai" OR "渋谷センター街"', 60)
        )
    )
    print(f"Commons Shibuya Center-gai candidate titles: {len(centergai_titles)}")
    all_records.extend(fetch_commons_imageinfo(centergai_titles, "shibuya_centergai"))

    # 2. Openverse
    all_records.extend(query_openverse_images("Shibuya Crossing", "shibuya_crossing", pages=3))
    all_records.extend(query_openverse_images("Shibuya Center-gai", "shibuya_centergai", pages=2))

    # Deduplicate by landing_url or original_url
    deduped: list[dict] = []
    seen_urls: set[str] = set()
    for r in all_records:
        key = r.get("original_url") or r.get("download_url")
        if not key or key in seen_urls:
            continue
        seen_urls.add(key)
        deduped.append(r)

    print(f"Total deduplicated modifiable+commercial candidates: {len(deduped)}")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(download_one, idx + 1, rec, photos_dir) for idx, rec in enumerate(deduped)]
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda r: (r["spot"], r.get("local_path", "")))
    ok = [r for r in results if r.get("status") in ("downloaded", "cached")]
    by_spot = {
        "shibuya_crossing": sum(1 for r in ok if r["spot"] == "shibuya_crossing"),
        "shibuya_centergai": sum(1 for r in ok if r["spot"] == "shibuya_centergai"),
    }
    by_license: dict[str, int] = {}
    for r in ok:
        by_license[r["license"]] = by_license.get(r["license"], 0) + 1

    payload = {
        "summary": {
            "total_candidates": len(deduped),
            "downloaded_ok": len(ok),
            "by_spot": by_spot,
            "by_license": by_license,
        },
        "photos": ok,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
