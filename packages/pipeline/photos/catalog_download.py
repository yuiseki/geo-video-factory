"""Download the photos of a commons_area_catalog within a radius, with a manifest of their sources.

    python -m photos.catalog_download <catalog.jsonl> <photos dir> <manifest.json> <flyover dir>
        --centre=lon,lat [--radius=600] [--known=<dir>,...]

Each photo is saved as NNN_<title>.jpg under <photos dir>; the manifest lists every row tried, in the layout
of the project's other photo manifests (local_path relative to <flyover dir>, licence, creator, landing URL),
with a status: downloaded, failed (and why), or "same picture already on disk" when its dHash equals a photo
under --known (so a copy of a photo we already have is not taken in twice). One download a second.
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


def _name(i, title):
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", title.split(":", 1)[-1])
    return f"{i:03d}_" + re.sub(r"[^0-9A-Za-z_-]+", "_", stem).strip("_")[:80] + ".jpg"


def download(rows, photos_dir, manifest_path, flyover_dir, fetch=None, sleep=time.sleep, known=()):
    fetch = fetch or (lambda url: download_bytes_with_retry(url)[0])     # (bytes, content type)
    photos_dir, flyover_dir = Path(photos_dir), Path(flyover_dir)
    photos_dir.mkdir(parents=True, exist_ok=True)
    seen = set(known)
    out = []
    for i, row in enumerate(rows, 1):
        rec = dict(row)
        path = photos_dir / _name(i, row["title"])
        if path.exists():                                     # a run that stopped part way: carry on
            seen.add(picture_hash(path.read_bytes()))
            rec.update(status="downloaded", local_path=str(path.relative_to(flyover_dir)), bytes=path.stat().st_size)
            out.append(rec)
            continue
        try:
            data = fetch(standard_thumb(row["download_url"]))
            h = picture_hash(data)
            if h in seen:
                rec["status"] = "same picture already on disk"
            else:
                seen.add(h)
                path.write_bytes(data)
                rec.update(status="downloaded", local_path=str(path.relative_to(flyover_dir)), bytes=len(data))
        except Exception as exc:   # recorded per photo: one broken file does not stop the set
            rec["status"] = f"failed: {exc}"
        out.append(rec)
        sleep(1.0)
    manifest = {"summary": {"rows": len(rows), "downloaded": sum(r["status"] == "downloaded" for r in out)},
                "photos": out}
    Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifest


def main(argv):
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    catalog, photos_dir, manifest, flyover = [a for a in argv if not a.startswith("--")][:4]
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
    m = download(rows, photos_dir, manifest, flyover, known=known)
    print(m["summary"])


if __name__ == "__main__":
    main(sys.argv[1:])
