"""Photos kept once per machine, by where they come from, and shared by every project.

A photo is named by a ref, "<source>:<id>", from the record of where it was found (photo_ref):

    commons:<file name>     Wikimedia Commons, the file name with "File:" dropped and spaces as underscores,
                            however it was found (Commons search, Openverse, an older manifest without a source)
    flickr:<photo id>       Flickr (through Openverse)
    rawpixel:<image id>     rawpixel
    wordpress:<photo id>    WordPress Photos

and kept under the shared cache (shared_cache.cache_root()) as photos/<source>/<sha1 of the id, 16>/, holding the
image (photo.<ext>) and meta.json: the ref, licence, creator, URLs, coordinates and date of the record, with the
picture's size, SHA-1 and dHash (also_sha1: the other copies of it seen, smaller ones not kept). Where a project happened to keep its copy (local_path, status) is not part of it.
The same photo found again, by any project, goes to the same place; the larger copy is kept.

A project names the photos it uses by ref (in its manifests, and the world model's cams.json as "ref"); path(ref)
finds the file, camera_photo(cam) a camera's photo, ref_of_file(file) the ref of any copy (by SHA-1). A photo on the blocklist
(photo_guard: share-alike licences and others never to be used again) is refused and never stored.

    python -m photos.photo_store import <manifest.json> <flyover dir>     take a project's downloaded photos in,
                                                                          and write each row's ref into the manifest
    python -m photos.photo_store refs <cams.json> ...                     name each world-model camera's photo by its ref
    python -m photos.photo_store fold <dir> ...                           a project's copies of stored photos become
                                                                          relative links to them (bytes kept once)
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

from PIL import Image

from photos import photo_guard, photo_use
from photos.photo_licences import is_registration_only

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


def camera_photo(cam: dict) -> Path:
    """The photo of a world-model camera (cams.json): the store when the camera names a ref, else its "photo" path.

    A camera is calibrated on one copy (its width): when the store kept a copy of another size (a larger one seen
    later), the camera's own "photo" path is used if it still exists, so the intrinsics fit the pixels."""
    if cam.get("ref"):
        found = path(cam["ref"])
        if found is not None:
            if "width" not in cam:
                return found
            with Image.open(found) as im:
                if im.width == int(cam["width"]):
                    return found
            if Path(cam["photo"]).exists():
                return Path(cam["photo"])
            return found
    return Path(cam["photo"])


_by_sha1: dict[str, dict[str, str]] = {}


def _sha1_index() -> dict[str, str]:
    """{sha1: ref} of every stored photo (read once per store root)."""
    from shared_cache import cache_root
    key = str(cache_root())
    if key not in _by_sha1:
        index = {}
        for meta in (cache_root() / "photos").glob("*/*/meta.json"):
            m = json.loads(meta.read_text(encoding="utf-8"))
            for sha1 in [m["sha1"], *m.get("also_sha1", [])]:
                index[sha1] = m["ref"]
        _by_sha1[key] = index
    return _by_sha1[key]


def ref_of_file(file) -> str | None:
    """The ref of a photo file: from its meta.json when it lies in the store, else from its bytes (SHA-1)."""
    file = Path(file).resolve()
    meta = file.parent / "meta.json"
    if file.name.startswith("photo.") and meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))["ref"]
    sha1 = hashlib.sha1(file.read_bytes()).hexdigest()
    index = _sha1_index()
    if sha1 not in index:                      # stored since the index was read
        _by_sha1.clear()
        index = _sha1_index()
    return index.get(sha1)


def add_refs(cams_path) -> dict[str, int]:
    """Write each camera's ref into a cams.json, for the photos the store has; "photo" is left as it was."""
    cams_path = Path(cams_path)
    cams = json.loads(cams_path.read_text(encoding="utf-8"))
    counts = {"named": 0, "not in the store": 0}
    for cam in cams.values():
        ref = ref_of_file(cam["photo"]) if Path(cam["photo"]).exists() else None
        if ref:
            cam["ref"] = ref
            counts["named"] += 1
        else:
            counts["not in the store"] += 1
    cams_path.write_text(json.dumps(cams, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return counts


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
    if row.get("use") == "registration":        # CC BY / BY-SA that only helps to place the others (photo_use)
        if not is_registration_only(row.get("license", ""), row.get("license_url", "")):
            raise BlockedPhoto(f"{ref}: {row.get('license')!r} is not taken for registration")
        ref = photo_use.registration_ref(ref)
    elif reason := blocked(data):
        raise BlockedPhoto(f"{ref}: {reason}")
    with Image.open(io.BytesIO(data)) as im:
        width, height, fmt = im.width, im.height, im.format
        dhash = photo_guard.dhash_of(im)
    d = _dir(ref)
    old = path(ref)
    sha1 = hashlib.sha1(data).hexdigest()
    seen: list[str] = []                               # every copy seen, so ref_of_file finds any of them
    if old is not None:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        seen = sorted(set(meta.get("also_sha1", [])) | {meta["sha1"]} - {sha1})
        if meta.get("width", 0) * meta.get("height", 0) >= width * height:
            if sha1 != meta["sha1"] and sha1 not in meta.get("also_sha1", []):
                meta["also_sha1"] = sorted(set(meta.get("also_sha1", [])) | {sha1})
                (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                _by_sha1.clear()
            return ref
        old.unlink()
    d.mkdir(parents=True, exist_ok=True)
    image = d / ("photo" + EXT.get(fmt, ".jpg"))
    part = image.with_name(image.name + ".part")
    part.write_bytes(data)
    part.replace(image)
    meta = {k: v for k, v in row.items() if k not in SKIP}
    meta.update(ref=ref, width=width, height=height, sha1=sha1, dhash=dhash)
    if seen:
        meta["also_sha1"] = seen
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return ref


def adopt(entries: list[dict], project_root, rejected) -> list[dict]:
    """Move photos a collector just wrote into the project (local_path) into the store.

    Each kept one gets its "photo" ref and loses its local_path; its project copy, written by that run, is
    removed. A photo the blocklist refuses is dropped and counted in rejected["blocklist"].
    """
    kept = []
    for entry in entries:
        file = Path(project_root) / entry["local_path"]
        try:
            entry["photo"] = put(entry, file.read_bytes())
            kept.append(entry)
        except BlockedPhoto:
            rejected["blocklist"] += 1
        file.unlink(missing_ok=True)
        entry.pop("local_path", None)
    return kept


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


def fold(folder) -> dict[str, int]:
    """Replace every file under `folder` that is byte for byte a stored photo (its meta.json "sha1", not a smaller
    copy listed in also_sha1, which a camera may be calibrated on) by a relative link to it, so that what refers to
    the project's path keeps working and the bytes are kept once; other files are left as they are."""
    from shared_cache import cache_root
    primary = {}
    for meta in (cache_root() / "photos").glob("*/*/meta.json"):
        m = json.loads(meta.read_text(encoding="utf-8"))
        found = next(iter(sorted(meta.parent.glob("photo.*"))), None)
        if found is not None:
            primary[m["sha1"]] = found
    counts = {"linked": 0, "kept": 0}
    for file in sorted(Path(folder).rglob("*")):
        if file.is_symlink() or not file.is_file():
            continue
        target = primary.get(hashlib.sha1(file.read_bytes()).hexdigest())
        if target is None:
            counts["kept"] += 1
            continue
        link = file.with_name(file.name + ".link")
        link.symlink_to(os.path.relpath(target.resolve(), file.parent.resolve()))
        link.replace(file)
        counts["linked"] += 1
    return counts


def main(argv: list[str]) -> None:
    if len(argv) == 3 and argv[0] == "import":
        print(json.dumps(import_manifest(Path(argv[1]), Path(argv[2]))))
        return
    if len(argv) >= 2 and argv[0] == "fold":
        for d in argv[1:]:
            print(d, json.dumps(fold(Path(d))))
        return
    if len(argv) >= 2 and argv[0] == "refs":
        for f in argv[1:]:
            print(f, json.dumps(add_refs(Path(f))))
        return
    raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
