"""The owner's Gyazo photos tagged #publish_as_cc0: their own photographs, released as CC0, with the place in EXIF.

A Gyazo id opens the photo, so ids stay out of the repository: the rows live in a gyazo.json that the repository
ignores (next to the catalogue that uses it, one photo per line, sorted), the photos in the shared store as
"gyazo:<id>", and a step reads them only when given --include-gyazo (atlas_before.py photos).

    python -m photos.gyazo_photos collect <gyazo.json> --creator=<name> [--query=#publish_as_cc0]

collect asks the gyazo CLI for every capture the query finds, reads each one's EXIF place (gyazo get), keeps the
public ones that carry the tag, stores each photo once and adds new rows to the file.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from photos import photo_store
from photos.photo_catalog_rules import classify_time_of_day
from photos.photo_licences import CC0_URL

TAG = "#publish_as_cc0"
TOKYO = timezone(timedelta(hours=9))


def record(item: dict, creator: str) -> dict | None:
    """A catalogue row of one Gyazo capture, or None unless it is public and tagged."""
    meta = item.get("metadata") or {}
    if item.get("access_policy") != "anyone" or TAG not in str(meta.get("desc") or ""):
        return None
    exif = meta.get("exif_normalized") or {}
    lat, lon = exif.get("latitude"), exif.get("longitude")
    when = exif.get("time") or item.get("created_at")
    local = datetime.fromisoformat(str(when).replace("Z", "+00:00")).astimezone(TOKYO) if when else None
    return {"source": "gyazo", "gyazo_id": item["image_id"], "title": f"Gyazo {item['image_id']}",
            "creator": creator, "license": "CC0", "license_url": CC0_URL,
            "landing_url": item.get("permalink_url"), "original_url": item.get("url"),
            "coordinates": [lon, lat] if lat is not None and lon is not None else None,
            "date": local.date().isoformat() if local else None,
            "time_of_day": classify_time_of_day("", hour=local.hour) if local else "unknown",
            "heading": _number((meta.get("exif") or {}).get("GPS Image Direction")),      # compass, degrees
            "focal_35mm": _number((meta.get("exif") or {}).get("Focal Length in 35mm Film"))}


def merge(found: dict, got: dict) -> dict:
    """A capture's detail (gyazo get: EXIF) with the description and access of its search result where the detail
    lacks them (gyazo get does not always return the description)."""
    meta = dict(found.get("metadata") or {}, **{k: v for k, v in (got.get("metadata") or {}).items() if v is not None})
    out = dict(found, **{k: v for k, v in got.items() if v is not None and k != "metadata"})
    out["metadata"] = meta
    return out


def _number(text) -> float | None:
    try:
        return float(str(text).split()[0])
    except (ValueError, IndexError):
        return None


def distance_m(a, b) -> float:
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def near(rows: list[dict], centre, radius_m: float) -> list[dict]:
    """The rows taken within radius_m of centre (lon, lat); rows without a place are left out."""
    return [r for r in rows if r.get("coordinates") and distance_m(r["coordinates"], centre) <= radius_m]


def read(path) -> list[dict]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))["photos"] if path.exists() else []


def write(path, rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: r["photo"])
    body = ",\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
    Path(path).write_text('{"photos": [\n' + body + "\n]}\n", encoding="utf-8")


def _gyazo(*args) -> object:
    out = subprocess.run(["gyazo", *args, "-j"], capture_output=True, text=True, timeout=120, check=True).stdout
    return json.loads(out)


def collect(path, creator: str, query: str = TAG) -> dict[str, int]:
    rows = read(path)
    known = {r["gyazo_id"] for r in rows}
    counts = {"new": 0, "known": 0, "refused": 0}
    page = 1
    while True:
        found = _gyazo("search", query, "-l", "100", "-p", str(page))
        found = found if isinstance(found, list) else found.get("images", [])
        if not found:
            break
        for item in found:
            if item["image_id"] in known:
                counts["known"] += 1
                continue
            row = record(merge(item, _gyazo("get", item["image_id"])), creator)
            if row is None:
                counts["refused"] += 1
                continue
            with urllib.request.urlopen(row["original_url"], timeout=60) as r:
                row["photo"] = photo_store.put(row, r.read())
            rows.append(row)
            known.add(row["gyazo_id"])
            counts["new"] += 1
        page += 1
    write(path, rows)
    return counts


def main(argv: list[str]) -> None:
    opts = dict((a[2:].split("=", 1) + [""])[:2] for a in argv if a.startswith("--"))
    args = [a for a in argv if not a.startswith("--")]
    if len(args) == 2 and args[0] == "collect" and opts.get("creator"):
        print(json.dumps(collect(Path(args[1]), opts["creator"], opts.get("query") or TAG)))
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
