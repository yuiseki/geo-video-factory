"""Wikimedia Commons & Openverse API query and retry helpers for photo catalogs."""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parents[1]) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from photos.photo_catalog_rules import _license_allowed, licence_name_and_url, strip_html

USER_AGENT = "GeoVideoFactoryPhotoCollector/2.0 (https://github.com/yuiseki/geo-video-factory)"


def _retry_wait_seconds(exc: Exception, attempt: int, delays: tuple[int, ...] = (3, 8, 20, 45)) -> float:
    base = float(delays[min(attempt, len(delays) - 1)])
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 429 and exc.headers:
        ra = exc.headers.get("Retry-After")
        if ra:
            try:
                return min(60.0, max(1.0, float(ra.strip())))
            except ValueError:
                pass
    return base


def fetch_json_with_retry(
    url: str,
    timeout: int = 25,
    max_retries: int = 4,
    sleep_fn=time.sleep,
    opener=urllib.request.urlopen,
) -> dict:
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with opener(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                sleep_fn(_retry_wait_seconds(exc, attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < max_retries:
                sleep_fn(_retry_wait_seconds(exc, attempt))
                continue
            raise
    assert last_exc is not None
    raise last_exc


def download_bytes_with_retry(
    url: str,
    timeout: int = 30,
    max_retries: int = 4,
    sleep_fn=time.sleep,
    opener=urllib.request.urlopen,
) -> tuple[bytes, str]:
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with opener(req, timeout=timeout) as resp:
                ctype = resp.headers.get("Content-Type", "")
                data = resp.read()
                return data, ctype
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                sleep_fn(_retry_wait_seconds(exc, attempt))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < max_retries:
                sleep_fn(_retry_wait_seconds(exc, attempt))
                continue
            raise
    assert last_exc is not None
    raise last_exc


def query_commons_search(
    query: str,
    limit: int = 80,
    license_mode: str = "cc0",
    sleep_fn=time.sleep,
    fetch_fn=None,
) -> list[str]:
    """Search Commons files; restrict to Category:CC-Zero when license_mode=='cc0'. license_mode=='cc0_pd' runs that
    search and a second one for files whose copyright status is public domain (structured data P6216=Q19652), and
    merges them (CC0 first): neither needs attribution. Licences are checked again on each file's page."""
    if license_mode == "cc0_pd":
        titles = query_commons_search(query, limit, "cc0", sleep_fn, fetch_fn)
        for t in query_commons_search(query, limit, "pd", sleep_fn, fetch_fn):
            if t not in titles:
                titles.append(t)
        return titles[:limit]
    fetcher = fetch_fn or fetch_json_with_retry
    titles: list[str] = []
    sroffset = 0
    if license_mode == "ccby_nosa":
        srsearch = f"{query.strip()} filetype:bitmap"
    elif license_mode == "pd":
        srsearch = f"{query.strip()} haswbstatement:P6216=Q19652 filetype:bitmap"
    else:
        srsearch = f'{query.strip()} incategory:"CC-Zero" filetype:bitmap'
    while len(titles) < limit:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": srsearch,
            "srnamespace": "6",
            "srlimit": str(min(50, limit - len(titles))),
            "sroffset": str(sroffset),
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        try:
            data = fetcher(url, sleep_fn=sleep_fn)
        except Exception as exc:
            print(f"[commons search warn] {query}: {exc}", file=sys.stderr)
            break
        batch = data.get("query", {}).get("search", [])
        if not batch:
            break
        for item in batch:
            titles.append(item["title"])
        if "continue" not in data:
            break
        sroffset = data["continue"].get("sroffset", sroffset + len(batch))
        sleep_fn(0.35)
    return titles


def query_commons_category(
    category: str,
    limit: int = 120,
    sleep_fn=time.sleep,
    fetch_fn=None,
) -> list[str]:
    fetcher = fetch_fn or fetch_json_with_retry
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
            data = fetcher(url, sleep_fn=sleep_fn)
        except Exception as exc:
            print(f"[commons category warn] {cat_name}: {exc}", file=sys.stderr)
            break
        for item in data.get("query", {}).get("categorymembers", []):
            titles.append(item["title"])
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
        sleep_fn(0.35)
    return titles


def query_commons_geosearch(
    lat: float,
    lon: float,
    radius_m: int = 300,
    limit: int = 80,
    sleep_fn=time.sleep,
    fetch_fn=None,
) -> list[str]:
    fetcher = fetch_fn or fetch_json_with_retry
    params = {
        "action": "query",
        "list": "geosearch",
        "gscoord": f"{lat}|{lon}",
        "gsradius": str(min(10000, max(10, int(radius_m)))),
        "gsnamespace": "6",
        "gslimit": str(min(500, max(1, int(limit)))),
        "format": "json",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    try:
        data = fetcher(url, sleep_fn=sleep_fn)
    except Exception as exc:
        print(f"[commons geosearch warn] {lat},{lon}: {exc}", file=sys.stderr)
        return []
    sleep_fn(0.35)
    return [item["title"] for item in data.get("query", {}).get("geosearch", []) if "title" in item]


def fetch_commons_details(
    titles: list[str],
    license_mode: str = "cc0",
    sleep_fn=time.sleep,
    fetch_fn=None,
) -> list[dict]:
    fetcher = fetch_fn or fetch_json_with_retry
    records: list[dict] = []
    for i in range(0, len(titles), 25):
        chunk = titles[i : i + 25]
        params = {
            "action": "query",
            "titles": "|".join(chunk),
            "prop": "imageinfo|coordinates|categories",
            "iiprop": "url|extmetadata|mime|size",
            "iiurlwidth": "2560",
            "cllimit": "30",
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        try:
            data = fetcher(url, sleep_fn=sleep_fn)
        except Exception as exc:
            print(f"[commons details warn] batch {i}: {exc}", file=sys.stderr)
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
            orig_w = int(info.get("width") or 0)
            orig_h = int(info.get("height") or 0)
            if max(orig_w, orig_h) < 1200:
                continue
            meta = info.get("extmetadata", {})
            lic_short = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
            lic_url = strip_html(meta.get("LicenseUrl", {}).get("value", ""))
            if not _license_allowed(lic_short, lic_url, license_mode):
                continue
            lic_short, lic_url = licence_name_and_url(lic_short, lic_url)

            artist = strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown"
            desc = strip_html(meta.get("ImageDescription", {}).get("value", ""))
            dt = strip_html(meta.get("DateTimeOriginal", {}).get("value", ""))
            cats = " | ".join(
                c.get("title", "") for c in page.get("categories", []) if c.get("title")
            )
            coords_list = page.get("coordinates") or []
            coords = None
            if coords_list and "lon" in coords_list[0] and "lat" in coords_list[0]:
                coords = [float(coords_list[0]["lon"]), float(coords_list[0]["lat"])]

            records.append(
                {
                    "source": "wikimedia_commons",
                    "title": page.get("title", ""),
                    "creator": artist[:120],
                    "license": lic_short,
                    "license_url": lic_url,
                    "description": desc[:300],
                    "categories": cats[:400],
                    "datetime": dt[:80],
                    "mime": mime,
                    "download_url": info.get("thumburl") or info.get("url"),
                    "original_url": info.get("url"),
                    "landing_url": info.get("descriptionurl"),
                    "orig_width": orig_w,
                    "orig_height": orig_h,
                    "orig_bytes": int(info.get("size") or 0),
                    "coordinates": coords,
                }
            )
        sleep_fn(0.35)
    return records


def query_openverse(
    query: str,
    pages: int = 3,
    skip_rawpixel: bool = True,
    license_mode: str = "cc0",
    sleep_fn=time.sleep,
    fetch_fn=None,
) -> list[dict]:
    fetcher = fetch_fn or fetch_json_with_retry
    records: list[dict] = []
    lic_param = {"ccby_nosa": "cc0,by", "cc0_pd": "cc0,pdm"}.get(license_mode, "cc0")
    allowed_codes = set(lic_param.split(","))
    for page in range(1, pages + 1):
        params = {
            "q": query,
            "license": lic_param,
            "category": "photograph",
            "page_size": "20",
            "page": str(page),
        }
        url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)
        try:
            data = fetcher(url, sleep_fn=sleep_fn)
        except Exception as exc:
            print(f"[openverse warn] {query} p{page}: {exc}", file=sys.stderr)
            break
        results = data.get("results", [])
        if not results:
            break
        for r in results:
            lic = (r.get("license") or "").strip().lower()
            if lic not in allowed_codes:
                continue
            lic_ver = (r.get("license_version") or "4.0").strip()
            lic_str = {"cc0": "CC0 1.0", "pdm": "Public Domain Mark 1.0"}.get(lic) or f"CC BY {lic_ver}".strip()
            src = (r.get("source") or "unknown").strip().lower()
            if skip_rawpixel and src == "rawpixel":
                continue
            img_url = r.get("url")
            if not img_url:
                continue
            w = int(r.get("width") or 0)
            h = int(r.get("height") or 0)
            if w > 0 and h > 0 and max(w, h) < 1200:
                continue
            records.append(
                {
                    "source": f"openverse/{src}",
                    "title": r.get("title") or r.get("id") or "untitled",
                    "creator": (r.get("creator") or "Unknown")[:120],
                    "license": lic_str,
                    "license_url": r.get("license_url")
                    or {"cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
                        "pdm": "https://creativecommons.org/publicdomain/mark/1.0/"}.get(lic)
                    or f"https://creativecommons.org/licenses/by/{lic_ver}/",
                    "description": "",
                    "categories": "",
                    "datetime": "",
                    "mime": "",
                    "download_url": img_url,
                    "original_url": img_url,
                    "landing_url": r.get("foreign_landing_url") or img_url,
                    "orig_width": w,
                    "orig_height": h,
                    "orig_bytes": 0,
                    "coordinates": None,
                }
            )
        sleep_fn(0.35)
    return records


def query_openverse_cc0(
    query: str,
    pages: int = 3,
    skip_rawpixel: bool = True,
    sleep_fn=time.sleep,
    fetch_fn=None,
) -> list[dict]:
    return query_openverse(
        query, pages=pages, skip_rawpixel=skip_rawpixel, license_mode="cc0", sleep_fn=sleep_fn, fetch_fn=fetch_fn
    )
