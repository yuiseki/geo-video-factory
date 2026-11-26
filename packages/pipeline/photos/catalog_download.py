"""Download the photos of a commons_area_catalog within a radius, with a manifest of their sources.

    python -m photos.catalog_download <catalog.jsonl> <manifest.json> --centre=lon,lat [--radius=600] [--known=<dir>,...]

Each photo goes to the shared photo store (photos.photo_store), once per machine for every project; the manifest
lists every row tried with its sources (licence, creator, landing URL), its ref ("photo": "commons:...") and a
status: downloaded, "in the store" (some project took it already: not fetched again), refused (on the
blocklist: never stored), failed (and why), or "same picture already on disk" when its dHash equals a photo
under --known. One download a second.
"""
from __future__ import annotations

import io
import json
import math
import re
import sys
import time
from pathlib import Path

from PIL import Image

from photos.photo_catalog_sources import download_bytes_with_retry
from photos.photo_guard import dhash_of


def within(rows, centre, radius_m):
    """Rows whose coordinates lie within radius_m of centre (lon, lat), in their order."""
    kx, ky = 111320.0 * math.cos(math.radians(centre[1])), 110950.0
    return [r for r in rows if r.get("coordinates")
            and math.hypot((r["coordinates"][0] - centre[0]) * kx, (r["coordinates"][1] - centre[1]) * ky) <= radius_m]


def picture_hash(data: bytes) -> str:
    with Image.open(io.BytesIO(data)) as im:
        return dhash_of(im)


def standard_thumb(url, width=1920):
    """A Commons thumbnail at one of the widths Wikimedia keeps rendered (1280, 1920, ...). Other widths are
    drawn on request and throttled: at 2560 px a download took about a minute."""
    return re.sub(r"/thumb/(.+)/\d+px-([^/]+)$", rf"/thumb/\1/{width}px-\2", url)


def download(rows, manifest_path, fetch=None, sleep=time.sleep, known=()):
    from photos import photo_store
    fetch = fetch or (lambda url: download_bytes_with_retry(url)[0])     # (bytes, content type)
    seen = set(known)
    out = []
    for row in rows:
        rec = dict(row)
        try:
            ref = photo_store.photo_ref(row)
        except ValueError as exc:
            rec["status"] = f"failed: {exc}"
            out.append(rec)
            continue
        if photo_store.path(ref) is not None:                 # any project took it already
            seen.add(picture_hash(photo_store.path(ref).read_bytes()))
            rec.update(status="in the store", photo=ref)
            out.append(rec)
            continue
        try:
            data = fetch(standard_thumb(row["download_url"]))
            h = picture_hash(data)
            if h in seen:
                rec["status"] = "same picture already on disk"
            else:
                seen.add(h)
                rec.update(status="downloaded", photo=photo_store.put(row, data), bytes=len(data))
        except photo_store.BlockedPhoto as exc:
            rec["status"] = f"refused: {exc}"
        except Exception as exc:   # recorded per photo: one broken file does not stop the set
            rec["status"] = f"failed: {exc}"
        out.append(rec)
        sleep(1.0)
    manifest = {"summary": {"rows": len(rows), "downloaded": sum(r["status"] == "downloaded" for r in out),
                            "in the store": sum(r["status"] == "in the store" for r in out)},
                "photos": out}
    Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifest


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    catalog, manifest = [a for a in argv if not a.startswith("--")][:2]
    rows = [json.loads(line) for line in Path(catalog).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = within(rows, tuple(float(v) for v in opts["centre"].split(",")), float(opts.get("radius", 600)))
    known = set()
    for d in [d for d in opts.get("known", "").split(",") if d]:
        for f in Path(d).rglob("*"):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                try:
                    with Image.open(f) as im:
                        known.add(dhash_of(im))
                except OSError:
                    pass
    print(f"{len(rows)} rows in the radius, {len(known)} pictures already on disk", flush=True)
    m = download(rows, manifest, known=known)
    print(m["summary"])


if __name__ == "__main__":
    main(sys.argv[1:])
