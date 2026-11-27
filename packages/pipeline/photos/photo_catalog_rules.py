"""License, urban-scene, datetime/season/time/weather rules, and diversity selection for photo catalogs."""
from __future__ import annotations

from collections import defaultdict
import html
import re

GITLEAKS_HEX32_RE = re.compile(r"(?:^|[^0-9a-fA-F])([0-9a-f]{32})(?:[^0-9a-fA-F]|$)")

DISALLOWED_LICENSE_RE = re.compile(
    r"(?:^|[^a-zA-Z])(?:NC|ND|SA|BY|PDM|GPL|GFDL)(?:[^a-zA-Z]|$)|PD-|Public\s*domain|Copyright|Fair\s*use|Attribution|ShareAlike|NoDerivatives|NonCommercial",
    re.IGNORECASE,
)

NOISE_KEYWORDS = (
    "ramen", "sushi", "udon", "soba", "bento", "curry", "izakaya menu",
    "food", "dish", "meal", "dessert", "cake", "coffee cup", "latte",
    "cosplay", "figurine", "figure", "doll", "plush", "maid cafe",
    "ticket", "receipt", "book cover", "magazine", "ukiyo-e", "woodblock",
    "painting", "engraving", "map of", "route map", "floor plan", "diagram",
    "chart", "screenshot", "logo", "icon", "emblem", "coat of arms",
    "barcode", "packaging", "ramen bowl",
    "メニュー", "ラーメン", "定食", "弁当", "寿司", "うどん", "蕎麦",
    "切符", "乗車券", "路線図", "地図", "浮世絵", "錦絵", "ロゴ", "図面",
    "商品パッケージ", "コスプレ", "フィギュア",
)

MONTH_NAMES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(text or ""))).strip()


def is_strict_cc0(license_short: str, license_url: str = "") -> bool:
    """Return True strictly for CC0 / CC-Zero licenses only."""
    short = (license_short or "").strip()
    url = (license_url or "").strip().lower()
    if short and DISALLOWED_LICENSE_RE.search(short):
        return False
    low = short.lower()
    if low in ("cc0", "cc0 1.0", "cc-zero", "cc0-1.0", "cc0 1.0 universal"):
        return True
    if low.startswith("cc0 ") or low.startswith("cc-zero"):
        return True
    if "creativecommons.org/publicdomain/zero/1.0" in url and (
        not short or "no restriction" in low or "cc0" in low or "zero" in low
    ):
        return True
    return False


def is_ccby_nosa_or_cc0(license_short: str, license_url: str = "") -> bool:
    """Return True for CC0 / CC-Zero or CC BY (non-SA, non-NC, non-ND) licenses."""
    if is_strict_cc0(license_short, license_url):
        return True
    short = (license_short or "").strip()
    url = (license_url or "").strip().lower()
    if re.search(
        r"(?:^|[^a-zA-Z])(?:NC|ND|SA|PDM|GPL|GFDL)(?:[^a-zA-Z]|$)|PD-|Public\s*domain|Copyright|Fair\s*use|ShareAlike|NoDerivatives|NonCommercial",
        short,
        re.IGNORECASE,
    ):
        return False
    low = short.lower()
    if re.search(r"(?:^|[^a-z])cc[ -]by(?:\s|$|[0-9-])", low):
        return True
    if "creativecommons.org/licenses/by/" in url:
        return True
    return False


CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"


def licence_name_and_url(license_short: str, license_url: str) -> tuple[str, str]:
    """Fill in a missing licence name or URL from the other one, for a licence that already passed the filter.

    Nothing is assumed to be CC0: an attribution licence known only by its URL keeps its own name, and one known
    only by a name without a version gets no URL rather than a guessed one."""
    short, url = (license_short or "").strip(), (license_url or "").strip()
    if is_strict_cc0(short, url):
        return short or "CC0", url or CC0_URL
    by_url = re.search(r"creativecommons\.org/licenses/by/(\d+(?:\.\d+)?)", url, re.IGNORECASE)
    if not short and by_url:
        short = f"CC BY {by_url.group(1)}"
    by_name = re.fullmatch(r"cc[ -]by[ -](\d+(?:\.\d+)?)", short, re.IGNORECASE)
    if not url and by_name:
        url = f"https://creativecommons.org/licenses/by/{by_name.group(1)}/"
    return short, url


def is_cc0_or_public_domain(license_short: str, license_url: str = "") -> bool:
    """CC0, or public domain (Commons' "Public domain", PD-* templates, the Public Domain Mark): no attribution
    needed and no share-alike. Anything with BY, SA or NC in it is refused."""
    if is_strict_cc0(license_short, license_url):
        return True
    low = (license_short or "").strip().lower()
    if not low or re.search(r"\b(by|sa|nc|nd|gfdl)\b", low):
        return False
    return low.startswith(("public domain", "pd-", "pd ", "pdm")) or low == "pd" or \
        "creativecommons.org/publicdomain/mark" in (license_url or "").lower()


def _license_allowed(license_short: str, license_url: str, license_mode: str) -> bool:
    if license_mode == "cc0_pd":
        return is_cc0_or_public_domain(license_short, license_url)
    if license_mode == "ccby_nosa":
        return is_ccby_nosa_or_cc0(license_short, license_url)
    return is_strict_cc0(license_short, license_url)


def date_rejection(year, license_short: str, license_url: str = "", min_year=None):
    """Why a photo is too old for a city as it stands now, or None. With min_year, a photo taken before it is refused,
    and so is a public-domain one without a date: public domain is mostly old prints, plans and postcards, where a
    CC0 file is the uploader's own photograph."""
    if not min_year:
        return None
    if year:
        return "before_min_year" if int(year) < int(min_year) else None
    return None if is_strict_cc0(license_short, license_url) else "pd_undated"


def is_urban_scene_candidate(rec: dict) -> tuple[bool, str]:
    """Filter out obvious non-urban photos (food, maps, tickets, cosplay, low-res, extreme aspect)."""
    w = int(rec.get("orig_width") or rec.get("width") or 0)
    h = int(rec.get("orig_height") or rec.get("height") or 0)
    if w > 0 and h > 0:
        if max(w, h) < 1200:
            return False, f"low_resolution:{w}x{h}"
        ratio = max(w, h) / max(1, min(w, h))
        if ratio > 4.0:
            return False, f"extreme_aspect:{ratio:.2f}"

    blob = " ".join(
        [rec.get("title", ""), rec.get("description", ""), rec.get("categories", "")]
    ).lower()
    for kw in NOISE_KEYWORDS:
        if re.search(r"[a-z]", kw):
            if re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", blob):
                return False, f"noise_keyword:{kw}"
        elif kw in blob:
            return False, f"noise_keyword:{kw}"
    return True, ""


def parse_datetime(text: str) -> dict:
    """Extract ISO-like date/year/month/hour from EXIF, Commons metadata, or filename text."""
    s = strip_html(text or "")
    if not s:
        return {"iso": None, "date": None, "year": None, "month": None, "hour": None}

    m = re.search(r"(\d{4})[:\-](\d{2})[:\-](\d{2})(?:[T\s]+(\d{2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hr = int(m.group(4)) if m.group(4) is not None else None
        mn = int(m.group(5)) if m.group(5) is not None else 0
        sc = int(m.group(6)) if m.group(6) is not None else 0
        if 1990 <= y <= 2035 and 1 <= mo <= 12 and 1 <= d <= 31:
            date_str = f"{y:04d}-{mo:02d}-{d:02d}"
            iso = f"{date_str}T{hr:02d}:{mn:02d}:{sc:02d}" if hr is not None else date_str
            return {"iso": iso, "date": date_str, "year": y, "month": mo, "hour": hr}

    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(19\d{2}|20\d{2})\b", s)
    if m and m.group(2).lower() in MONTH_NAMES:
        d, mo, y = int(m.group(1)), MONTH_NAMES[m.group(2).lower()], int(m.group(3))
        if 1 <= d <= 31:
            date_str = f"{y:04d}-{mo:02d}-{d:02d}"
            return {"iso": date_str, "date": date_str, "year": y, "month": mo, "hour": None}

    m = re.search(r"\b([A-Za-z]+)\s+(?:(\d{1,2}),?\s+)?(19\d{2}|20\d{2})\b", s)
    if m and m.group(1).lower() in MONTH_NAMES:
        mo = MONTH_NAMES[m.group(1).lower()]
        y = int(m.group(3))
        if m.group(2):
            d = int(m.group(2))
            date_str = f"{y:04d}-{mo:02d}-{d:02d}"
            return {"iso": date_str, "date": date_str, "year": y, "month": mo, "hour": None}
        date_str = f"{y:04d}-{mo:02d}"
        return {"iso": date_str, "date": date_str, "year": y, "month": mo, "hour": None}

    m = re.search(r"(?<!\d)(199\d|20[0-3]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        date_str = f"{y:04d}-{mo:02d}-{d:02d}"
        return {"iso": date_str, "date": date_str, "year": y, "month": mo, "hour": None}

    return {"iso": None, "date": None, "year": None, "month": None, "hour": None}


def classify_season(text: str, month: int | None = None) -> str:
    low = (text or "").lower()
    if any(k in low for k in ("sakura", "cherry blossom", "hanami", "桜", "花見", "新緑", "spring")):
        return "spring"
    if any(k in low for k in ("autumn", "fall foliage", "koyo", "momiji", "ginkgo", "紅葉", "黄葉", "銀杏", "イチョウ", "秋")):
        return "autumn"
    if any(k in low for k in ("winter", "snow", "illumination", "christmas", "冬", "雪", "イルミネーション")):
        return "winter"
    if any(k in low for k in ("summer", "matsuri", "fireworks", "夏", "梅雨")):
        return "summer"
    if month is not None:
        if month in (3, 4, 5):
            return "spring"
        if month in (6, 7, 8):
            return "summer"
        if month in (9, 10, 11):
            return "autumn"
        if month in (12, 1, 2):
            return "winter"
    return "unknown"


def classify_time_of_day(
    text: str,
    hour: int | None = None,
    luma: tuple[float, float] | None = None,
) -> str:
    low = (text or "").lower()
    if any(k in low for k in ("midnight", "nightview", "night view", "at night", "night", "neon", "夜", "夜景", "深夜", "夜間")):
        return "night"
    if any(k in low for k in ("dusk", "twilight", "sunset", "evening", "blue hour", "夕方", "夕暮れ", "黄昏", "日没", "夕")):
        return "dusk"
    if any(k in low for k in ("early morning", "morning", "sunrise", "dawn", "朝", "早朝", "日の出", "夜明け")):
        return "morning"
    if any(k in low for k in ("daytime", "afternoon", "midday", "noon", "昼", "日中", "午後")):
        if luma is not None and luma[0] < 35.0:
            return "night"
        return "day"

    mean_luma, top_luma = luma if luma is not None else (None, None)

    if hour is not None:
        if 5 <= hour <= 8:
            return "night" if (mean_luma is not None and mean_luma < 35.0) else "morning"
        if 9 <= hour <= 15:
            if mean_luma is not None and top_luma is not None and mean_luma < 42.0 and top_luma < 35.0:
                return "night"
            return "day"
        if 16 <= hour <= 18:
            return "night" if (mean_luma is not None and mean_luma < 38.0) else "dusk"
        if hour >= 19 or hour <= 4:
            if mean_luma is not None and top_luma is not None and mean_luma > 135.0 and top_luma > 145.0:
                return "day"
            return "night"

    if mean_luma is not None and top_luma is not None:
        if mean_luma < 58.0 or (mean_luma < 72.0 and top_luma < 50.0):
            return "night"
        if mean_luma < 92.0:
            return "dusk"
        return "day"

    return "unknown"


def classify_weather(text: str) -> str:
    low = (text or "").lower()
    if any(k in low for k in ("snow", "snowy", "blizzard", "雪", "積雪")):
        return "snow"
    if any(k in low for k in ("rain", "rainy", "wet", "drizzle", "umbrella", "typhoon", "雨", "雨天")):
        return "rain"
    if any(k in low for k in ("fog", "foggy", "mist", "misty", "haze", "霧", "靄")):
        return "fog"
    return "normal"


def safe_filename(seq: int, title: str, url: str, mime: str = "") -> str:
    ext = ".jpg"
    low_url = (url or "").lower().split("?")[0]
    low_mime = (mime or "").lower()
    if low_url.endswith(".png") or "png" in low_mime:
        ext = ".png"
    elif low_url.endswith(".webp") or "webp" in low_mime:
        ext = ".webp"
    elif low_url.endswith((".jpg", ".jpeg")) or "jpeg" in low_mime:
        ext = ".jpg"

    stem = re.sub(r"^File:", "", title or "")
    stem = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", stem)
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_")[:56] or "photo"
    return f"{seq:03d}_{stem}{ext}"


def find_gitleaks_hex32_matches(obj: object) -> list[str]:
    """Detect tokens of exactly 32 lowercase hex digits matching .gitleaks.toml."""
    found: list[str] = []

    def walk(val: object) -> None:
        if isinstance(val, dict):
            for v in val.values():
                walk(v)
        elif isinstance(val, (list, tuple)):
            for v in val:
                walk(v)
        elif isinstance(val, str):
            for m in GITLEAKS_HEX32_RE.finditer(val):
                found.append(m.group(1))

    walk(obj)
    return found


def sanitize_hex32_for_gitleaks(rec: dict) -> tuple[dict, list[str]]:
    """Strip 32-hex tokens from free-text fields; flag if URLs themselves contain one."""
    warnings: list[str] = []
    out = dict(rec)
    for url_key in ("original_url", "download_url", "landing_url"):
        val = out.get(url_key, "")
        if isinstance(val, str) and GITLEAKS_HEX32_RE.search(val):
            warnings.append(f"url_hex32:{url_key}")
    for text_key in ("title", "description", "categories", "creator"):
        val = out.get(text_key, "")
        if isinstance(val, str) and GITLEAKS_HEX32_RE.search(val):
            out[text_key] = GITLEAKS_HEX32_RE.sub(
                lambda m: m.group(0).replace(m.group(1), "[redacted-id]"), val
            )
            warnings.append(f"redacted_text:{text_key}")
    return out, warnings


def _score_candidate(rec: dict) -> int:
    score = 0
    if rec.get("time_of_day") in ("morning", "dusk", "night"):
        score += 15
    if rec.get("season") in ("spring", "autumn", "winter"):
        score += 15
    if rec.get("weather") != "normal":
        score += 10
    if rec.get("coordinates"):
        score += 10
    if rec.get("date"):
        score += 5
    if max(rec.get("orig_width") or 0, rec.get("orig_height") or 0) >= 2400:
        score += 10
    return score


def select_diverse_candidates(
    candidates: list[dict],
    limit: int = 80,
    max_per_creator_day: int = 2,
) -> list[dict]:
    """Round-robin across (spot_slug, time_of_day, season) buckets while capping burst shots."""
    if limit <= 0 or not candidates:
        return []

    buckets: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for rec in candidates:
        bkey = (
            rec.get("spot_slug", "unknown"),
            rec.get("time_of_day", "unknown"),
            rec.get("season", "unknown"),
        )
        buckets[bkey].append(rec)

    for bkey in buckets:
        buckets[bkey].sort(key=lambda r: (-(r.get("score") or 0), r.get("title", "")))

    ordered_keys = sorted(
        buckets.keys(),
        key=lambda k: (k[1] == "unknown", k[2] == "unknown", len(buckets[k]), k),
    )

    picked: list[dict] = []
    seen_keys: set[str] = set()
    creator_day_counts: dict[tuple[str, str, str], int] = defaultdict(int)

    progress = True
    while len(picked) < limit and progress:
        progress = False
        for bkey in ordered_keys:
            if len(picked) >= limit:
                break
            queue = buckets[bkey]
            while queue:
                cand = queue.pop(0)
                uniq = (cand.get("original_url") or cand.get("download_url") or cand.get("title") or "").lower()
                if uniq and uniq in seen_keys:
                    continue
                cd_key = (
                    (cand.get("creator") or "unknown").strip().lower(),
                    (cand.get("date") or "nodate")[:10],
                    cand.get("spot_slug", "unknown"),
                )
                cap = int(cand.get("max_per_creator_day") or max_per_creator_day)
                if creator_day_counts[cd_key] >= cap:
                    continue
                if uniq:
                    seen_keys.add(uniq)
                creator_day_counts[cd_key] += 1
                picked.append(cand)
                progress = True
                break

    return picked
