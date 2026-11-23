#!/usr/bin/env python3
"""Collect high-resolution (iiurlwidth >= 2400) commercially usable, modifiable
night facade photos of Shibuya Crossing buildings from Wikimedia Commons and Openverse.
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
from PIL import Image


USER_AGENT = "GeoVideoFactoryPhotoCollector/1.1 (https://github.com/yuiseki/geo-video-factory)"

DISALLOWED_RE = re.compile(r"(NC|ND|NonCommercial|NoDerivatives|Copyrighted|Fair use)", re.IGNORECASE)


def is_modifiable_commercial_license(license_str: str) -> tuple[bool, bool]:
    """Return (allowed, is_share_alike)."""
    s = (license_str or "").strip()
    if not s or DISALLOWED_RE.search(s):
        return False, False
    low = s.lower()
    if "cc0" in low or "public domain" in low or low == "pdm" or "pd-" in low:
        return True, False
    if "cc-by-sa" in low or "cc by-sa" in low or low == "by-sa":
        return True, True
    if "cc-by" in low or "cc by" in low or low == "by":
        return True, False
    return False, False


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(text or ""))).strip()


def fetch_json(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def query_commons_category(category: str, limit: int = 120) -> list[str]:
    titles: list[str] = []
    cmcontinue = None
    cat_name = category if category.startswith("Category:") else f"Category:{category}"
    while len(titles) < limit:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": cat_name,
            "cmtype": "file",
            "cmlimit": str(min(50, limit - len(titles))),
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"Category error ({cat_name}): {exc}")
            break
        for item in data.get("query", {}).get("categorymembers", []):
            titles.append(item["title"])
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    return titles


def query_commons_search(query: str, limit: int = 80) -> list[str]:
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
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"Search error ({query}): {exc}")
            break
        batch = data.get("query", {}).get("search", [])
        if not batch:
            break
        for item in batch:
            titles.append(item["title"])
        if "continue" not in data:
            break
        sroffset = data["continue"].get("sroffset", sroffset + len(batch))
    return titles


def fetch_commons_imageinfo(titles: list[str], tag_map: dict[str, str]) -> list[dict]:
    records: list[dict] = []
    for i in range(0, len(titles), 25):
        chunk = titles[i : i + 25]
        params = {
            "action": "query",
            "titles": "|".join(chunk),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime|size",
            "iiurlwidth": "2560",
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"Imageinfo error: {exc}")
            continue
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            info = infos[0]
            mime = info.get("mime", "")
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                continue
            orig_w = info.get("width") or 0
            orig_h = info.get("height") or 0
            if orig_w < 1200 and orig_h < 1200:
                continue
            meta = info.get("extmetadata", {})
            lic = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
            allowed, share_alike = is_modifiable_commercial_license(lic)
            if not allowed:
                continue
            artist = strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown"
            desc = strip_html(meta.get("ImageDescription", {}).get("value", ""))
            categories = strip_html(meta.get("Categories", {}).get("value", ""))
            dt = strip_html(meta.get("DateTimeOriginal", {}).get("value", ""))
            download_url = info.get("thumburl") or info.get("url")
            orig_url = info.get("url")
            landing_url = info.get("descriptionurl")
            title = page.get("title", "")
            records.append(
                {
                    "spot": "shibuya_buildings_night",
                    "query_tag": tag_map.get(title, "commons"),
                    "source": "wikimedia_commons",
                    "title": title,
                    "creator": artist,
                    "license": lic,
                    "share_alike": share_alike,
                    "description": desc[:300],
                    "categories": categories[:300],
                    "datetime": dt[:60],
                    "download_url": download_url,
                    "original_url": orig_url,
                    "landing_url": landing_url,
                    "width": info.get("thumbwidth") or orig_w,
                    "height": info.get("thumbheight") or orig_h,
                    "orig_width": orig_w,
                    "orig_height": orig_h,
                }
            )
    return records


def query_openverse_images(query: str, tag: str, pages: int = 2) -> list[dict]:
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
            w = r.get("width") or 0
            h = r.get("height") or 0
            if w and h and w < 1200 and h < 1200:
                continue
            records.append(
                {
                    "spot": "shibuya_buildings_night",
                    "query_tag": tag,
                    "source": f"openverse/{r.get('source', 'unknown')}",
                    "title": r.get("title") or r.get("id") or "untitled",
                    "creator": r.get("creator") or "Unknown",
                    "license": lic_str,
                    "share_alike": share_alike,
                    "description": "",
                    "categories": "",
                    "datetime": "",
                    "download_url": img_url,
                    "original_url": img_url,
                    "landing_url": r.get("foreign_landing_url") or img_url,
                    "width": w,
                    "height": h,
                    "orig_width": w,
                    "orig_height": h,
                }
            )
        time.sleep(0.35)
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


def download_one(idx: int, rec: dict, out_dir: Path, project_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = safe_filename(idx, rec["title"], rec["download_url"])
    out_path = out_dir / fname
    if out_path.exists() and out_path.stat().st_size > 2048:
        rec["local_path"] = str(out_path.relative_to(project_dir / "flyover"))
        rec["status"] = "cached"
        try:
            with Image.open(out_path) as im:
                rec["width"], rec["height"] = im.size
        except Exception:
            pass
        return rec
    try:
        req = urllib.request.Request(rec["download_url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "image" not in ctype and not rec["download_url"].lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                rec["status"] = f"skipped_content_type:{ctype}"
                return rec
            data = resp.read()
        if len(data) < 4096:
            rec["status"] = "skipped_too_small"
            return rec
        out_path.write_bytes(data)
        try:
            with Image.open(out_path) as im:
                rec["width"], rec["height"] = im.size
        except Exception:
            pass
        rec["local_path"] = str(out_path.relative_to(project_dir / "flyover"))
        rec["bytes"] = len(data)
        rec["status"] = "downloaded"
    except Exception as exc:
        rec["status"] = f"error:{exc}"
    return rec


def is_likely_shibuya_relevant(rec: dict) -> bool:
    """Filter out unrelated files from broad categories unless priority-tagged."""
    if rec.get("query_tag", "").startswith("priority_"):
        return True
    blob = " ".join(
        [
            rec.get("title", ""),
            rec.get("description", ""),
            rec.get("categories", ""),
            rec.get("query_tag", ""),
        ]
    ).lower()
    keywords = [
        "shibuya",
        "crossing",
        "scramble",
        "qfront",
        "tsutaya",
        "109",
        "magnet",
        "hachiko",
        "center-gai",
        "center gai",
        "centergai",
        "dogenzaka",
        "udagawa",
        "jinnan",
        "seibu",
        "occitane",
        "nishimura",
        "taiseido",
        "sanzenri",
        "salonpas",
        "tokyu",
        "渋谷",
        "スクランブル",
        "ハチ公",
        "道玄坂",
        "宇田川",
        "神南",
        "西武",
        "ロクシタン",
        "西村",
        "大盛堂",
        "三千里",
    ]
    return any(k in blob for k in keywords)


def score_record(rec: dict) -> int:
    """Prioritize night / building-specific / high-res candidates."""
    tag = rec.get("query_tag", "")
    blob = " ".join(
        [
            rec.get("title", ""),
            rec.get("description", ""),
            rec.get("categories", ""),
            tag,
        ]
    ).lower()
    score = 0
    if tag.startswith("priority_"):
        score += 100
    for kw in ["occitane", "ロクシタン", "渋谷駅前ビル", "qfront", "tsutaya", "109men", "magnet", "nishimura", "西村", "三千里", "大盛堂", "seibu", "西武", "hachiko", "ハチ公"]:
        if kw in blob:
            score += 40
    for kw in ["night", "evening", "neon", "dusk", "夜景", "夜", "illuminat"]:
        if kw in blob:
            score += 35
    for kw in ["crossing", "scramble", "center-gai", "center gai", "センター街"]:
        if kw in blob:
            score += 20
    if (rec.get("orig_width") or 0) >= 2400:
        score += 15
    return score


def main() -> None:
    project_dir = Path(__file__).resolve().parents[2]
    out_dir = project_dir / "flyover/assets/photos/shibuya_buildings_night"
    manifest_path = project_dir / "research/photos_buildings_night_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    tag_map: dict[str, str] = {}

    def add_titles(titles: list[str], tag: str) -> None:
        for t in titles:
            if t not in tag_map:
                tag_map[t] = tag

    # 1. Wikimedia Commons Categories requested
    commons_categories = [
        ("Shibuya Crossing at night", "priority_cat_crossing_night", 150),
        ("QFRONT", "priority_cat_qfront", 120),
        ("Shibuya Center-gai at night", "priority_cat_centergai_night", 120),
        ("MAGNET by SHIBUYA109", "priority_cat_magnet109", 100),
        ("109MEN'S", "priority_cat_109mens", 100),
        ("Seibu Shibuya", "priority_cat_seibu", 100),
        ("Hachiko Square", "priority_cat_hachiko", 100),
        ("Shibuya Crossing", "cat_crossing", 150),
        ("Buildings in Shibuya", "cat_buildings_shibuya", 120),
        ("Dogenzaka", "cat_dogenzaka", 120),
        ("Jinnan, Shibuya", "cat_jinnan", 100),
        ("Udagawacho", "cat_udagawacho", 120),
        ("Night in Shibuya", "priority_cat_night_shibuya", 150),
    ]
    for cat, tag, lim in commons_categories:
        titles = query_commons_category(cat, lim)
        print(f"Commons Category:{cat} -> {len(titles)} files")
        add_titles(titles, tag)

    # 2. Wikimedia Commons Searches requested
    commons_queries = [
        ('"L\'Occitane" Shibuya', "priority_loccitane"),
        ("Loccitane Shibuya", "priority_loccitane"),
        ("L'Occitane Shibuya", "priority_loccitane"),
        ("ロクシタン 渋谷", "priority_loccitane"),
        ("渋谷駅前ビル", "priority_ekimae_bldg"),
        ("ガスト 渋谷", "priority_ekimae_bldg"),
        ("Shibuya Crossing night", "priority_crossing_night"),
        ("Shibuya Scramble night", "priority_scramble_night"),
        ("Shibuya at night", "priority_shibuya_night"),
        ("QFRONT", "priority_qfront"),
        ("Shibuya TSUTAYA", "priority_tsutaya"),
        ("109MEN'S", "priority_109mens"),
        ("MAGNET by SHIBUYA109", "priority_magnet109"),
        ("Shibuya Nishimura", "priority_nishimura"),
        ("西村總本店", "priority_nishimura"),
        ("渋谷西村", "priority_nishimura"),
        ("三千里薬品", "priority_sanzenri"),
        ("大盛堂書店", "priority_taiseido"),
        ("サロンパス 渋谷", "priority_salonpas"),
        ("Seibu Shibuya", "priority_seibu"),
        ("西武渋谷", "priority_seibu"),
        ("Hachiko Square night", "priority_hachiko_night"),
        ("Shibuya Station night", "priority_station_night"),
        ("渋谷スクランブル交差点 夜", "priority_crossing_night_ja"),
        ("道玄坂 夜", "priority_dogenzaka_night"),
    ]
    for q, tag in commons_queries:
        titles = query_commons_search(q, 60)
        print(f"Commons Search [{q}] -> {len(titles)} files")
        add_titles(titles, tag)

    all_titles = list(tag_map.keys())
    print(f"Total unique Commons titles to query imageinfo: {len(all_titles)}")
    all_records = fetch_commons_imageinfo(all_titles, tag_map)
    print(f"Commons licensed records fetched: {len(all_records)}")

    # 3. Openverse Searches requested
    openverse_queries = [
        ("L'Occitane Shibuya", "priority_ov_loccitane", 1),
        ("Loccitane Shibuya", "priority_ov_loccitane", 1),
        ("Shibuya Crossing night", "priority_ov_crossing_night", 3),
        ("Shibuya Scramble night", "priority_ov_scramble_night", 2),
        ("Shibuya at night", "priority_ov_shibuya_night", 3),
        ("QFRONT", "priority_ov_qfront", 2),
        ("Shibuya TSUTAYA", "priority_ov_tsutaya", 2),
        ("109MEN'S", "priority_ov_109mens", 1),
        ("MAGNET Shibuya", "priority_ov_magnet", 1),
        ("Seibu Shibuya", "priority_ov_seibu", 2),
        ("Hachiko Square night", "priority_ov_hachiko_night", 2),
        ("Shibuya Station night", "priority_ov_station_night", 2),
    ]
    for q, tag, pages in openverse_queries:
        recs = query_openverse_images(q, tag, pages=pages)
        print(f"Openverse [{q}] -> {len(recs)} records")
        all_records.extend(recs)

    # Deduplicate and filter
    deduped: list[dict] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for r in all_records:
        if not is_likely_shibuya_relevant(r):
            continue
        key = r.get("original_url") or r.get("download_url")
        t_key = r.get("title", "").lower()
        if not key or key in seen_urls or (t_key and t_key in seen_titles):
            continue
        seen_urls.add(key)
        if t_key:
            seen_titles.add(t_key)
        r["score"] = score_record(r)
        deduped.append(r)

    deduped.sort(key=lambda r: (-r["score"], r.get("title", "")))
    print(f"Total deduplicated relevant candidates: {len(deduped)}")

    # Download top 220 high-res candidates
    target_candidates = deduped[:220]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(download_one, idx + 1, rec, out_dir, project_dir)
            for idx, rec in enumerate(target_candidates)
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda r: r.get("local_path", "zzz"))
    ok = [r for r in results if r.get("status") in ("downloaded", "cached")]

    by_license: dict[str, int] = {}
    by_tag: dict[str, int] = {}
    for r in ok:
        by_license[r["license"]] = by_license.get(r["license"], 0) + 1
        by_tag[r["query_tag"]] = by_tag.get(r["query_tag"], 0) + 1

    payload = {
        "summary": {
            "total_candidates_discovered": len(deduped),
            "attempted_downloads": len(target_candidates),
            "downloaded_ok": len(ok),
            "output_dir": "flyover/assets/photos/shibuya_buildings_night",
            "by_license": by_license,
            "by_query_tag": by_tag,
        },
        "photos": ok,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
