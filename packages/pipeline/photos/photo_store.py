"""Photos kept once per machine, by where they come from, and shared by every project.

A photo is named by a ref, "<source>:<id>", from the record of where it was found (photo_ref):

    commons:<file name>     Wikimedia Commons, the file name with "File:" dropped and spaces as underscores,
                            however it was found (Commons search, Openverse, an older manifest without a source)
    flickr:<photo id>       Flickr (through Openverse)
    rawpixel:<image id>     rawpixel
    wordpress:<photo id>    WordPress Photos

and kept under the shared cache (shared_cache.cache_root()) as photos/<source>/<sha1 of the id, 16>/, holding the
image (photo.<ext>) and meta.json: the ref, licence, creator, URLs, coordinates and date of the record, with the
picture's size, SHA-1 and dHash. Where a project happened to keep its copy (local_path, status) is not part of it.
The same photo found again, by any project, goes to the same place; the larger copy is kept.

A project names the photos it uses by ref (in its manifests); path(ref) finds the file. A photo on the blocklist
(photo_guard: share-alike licences and others never to be used again) is refused and never stored.

    python -m photos.photo_store import <manifest.json> <flyover dir>     take a project's downloaded photos in,
                                                                          and write each row's ref into the manifest
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import urllib.parse
from pathlib import Path

from PIL import Image

from photos import photo_guard

SKIP = {"local_path", "status", "bytes"}
EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}


class BlockedPhoto(Exception):
    pass


def _commons_name(row: dict) -> str | None:
    title = str(row.get("title") or "")
    if title.startswith("File:"):
        return title[5:].replace(" ", "_")
    for key in ("original_url", "download_url", "landing_url"):
        url = str(row.get(key) or "")
        m = re.search(r"upload\.wikimedia\.org/wikipedia/commons/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/?]+)", url)
        if m:
            return urllib.parse.unquote(m.group(1)).replace(" ", "_")
        m = re.search(r"commons\.wikimedia\.org/wiki/File:([^?#]+)", url)
        if m:
            return urllib.parse.unquote(m.group(1)).replace(" ", "_")
    return None


def photo_ref(row: dict) -> str:
    """"<source>:<id>" of the photo a manifest row describes; ValueError when the row does not say."""
    source = str(row.get("source") or "")
    landing = str(row.get("landing_url") or "")
    if "flickr" in source or "flickr.com/photos/" in landing:
        m = re.search(r"flickr\.com/photos/[^/]+/(\d+)", landing)
        if m:
            return f"flickr:{m.group(1)}"
    if "rawpixel" in source or "rawpixel.com" in landing:
        m = re.search(r"rawpixel\.com/image/(\d+)", landing)
        if m:
            return f"rawpixel:{m.group(1)}"
    if "wordpress" in source or "wordpress.org/photos" in landing:
        m = re.search(r"wordpress\.org/photos/photo/([0-9a-z]+)", landing)
        if m:
            return f"wordpress:{m.group(1)}"
    if source in ("", "wikimedia_commons", "openverse/wikimedia") or "wikimedia.org" in landing:
        name = _commons_name(row)
        if name:
            return f"commons:{name}"
    raise ValueError(f"cannot tell which photo this is: {row.get('source')} {row.get('title')} {landing}")


def _dir(ref: str) -> Path:
    from shared_cache import cache_root
    source, ident = ref.split(":", 1)
    return cache_root() / "photos" / source / hashlib.sha1(ident.encode()).hexdigest()[:16]


def path(ref: str) -> Path | None:
    """The stored image of a ref, or None."""
    d = _dir(ref)
    return next(iter(sorted(d.glob("photo.*"))), None) if d.exists() else None


def photo_file(row: dict, project_root) -> Path:
    """Where a manifest row's photo is: the store when the row names it, else where the project kept its copy."""
    if row.get("photo"):
        found = path(row["photo"])
        if found is not None:
            return found
    return Path(project_root) / row["local_path"]


def blocked(data: bytes) -> str | None:
    """Why the photo may not be used (photo_guard's list), or None."""
    by_sha, by_hash = photo_guard._listed(photo_guard.BLOCKLIST)
    hit = by_sha.get(hashlib.sha1(data).hexdigest())
    if hit is None:
        with Image.open(io.BytesIO(data)) as im:
            h = int(photo_guard.dhash_of(im), 16)
        hit = next((r for v, r in by_hash if bin(v ^ h).count("1") <= photo_guard.MAX_DISTANCE), None)
    return None if hit is None else f"{hit['licence']}, {hit['title']}: {hit['reason']}"


def put(row: dict, data: bytes) -> str:
    """Keep the photo of a manifest row (its bytes as downloaded); returns its ref."""
    ref = photo_ref(row)
    reason = blocked(data)
    if reason:
        raise BlockedPhoto(f"{ref}: {reason}")
    with Image.open(io.BytesIO(data)) as im:
        width, height, fmt = im.width, im.height, im.format
        dhash = photo_guard.dhash_of(im)
    d = _dir(ref)
    old = path(ref)
    if old is not None:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        if meta.get("width", 0) * meta.get("height", 0) >= width * height:
            return ref
        old.unlink()
    d.mkdir(parents=True, exist_ok=True)
    image = d / ("photo" + EXT.get(fmt, ".jpg"))
    part = image.with_name(image.name + ".part")
    part.write_bytes(data)
    part.replace(image)
    meta = {k: v for k, v in row.items() if k not in SKIP}
    meta.update(ref=ref, width=width, height=height, sha1=hashlib.sha1(data).hexdigest(), dhash=dhash)
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return ref


def import_manifest(manifest_path: Path, flyover_dir: Path) -> dict[str, int]:
    """Take the downloaded photos of a project manifest into the store; each such row gets its "photo" ref."""
    manifest_path, flyover_dir = Path(manifest_path), Path(flyover_dir)
    raw = manifest_path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    indent = next((i for i in (1, 2, 4) if raw.startswith(("{\n" if isinstance(doc, dict) else "[\n") + " " * i + '"')
                   or raw.startswith("[\n" + " " * i + "{")), 2)
    rows = doc["photos"] if isinstance(doc, dict) else doc
    counts = {"stored": 0, "blocked": 0, "missing": 0, "unknown": 0}
    for row in rows:
        if not isinstance(row, dict) or not row.get("local_path"):
            continue
        file = flyover_dir / row["local_path"]
        if not file.exists():
            counts["missing"] += 1
            continue
        try:
            row["photo"] = put(row, file.read_bytes())
            counts["stored"] += 1
        except BlockedPhoto:
            counts["blocked"] += 1
        except ValueError:
            counts["unknown"] += 1
    manifest_path.write_text(json.dumps(doc, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8")   # as it was laid out
    return counts


def main(argv: list[str]) -> None:
    if len(argv) == 3 and argv[0] == "import":
        print(json.dumps(import_manifest(Path(argv[1]), Path(argv[2]))))
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
