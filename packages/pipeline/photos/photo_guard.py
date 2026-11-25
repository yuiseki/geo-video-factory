"""Photos that must never be used again, refused wherever a photo is read.

photo_blocklist.tsv lists them (one row per photo, sorted): the SHA-1 of the file as downloaded, a 64-bit
difference hash (dHash) of the picture, the licence, the source title and why. A photo is refused when its
SHA-1 matches, or when its dHash is within MAX_DISTANCE bits of a listed one, so a resized or recompressed
copy of a listed photo is refused too.

Share-alike photos (CC BY-SA) are listed because a video that paints them onto buildings is an adaptation,
which would then have to be released under the same licence. They are kept on disk and in the list, not
deleted, so that a later download of the same picture is caught.

    python photo_guard.py add <licence> <title> <reason> <photo> ...     add photos to the list
    python photo_guard.py check <photo> ...                                exit 1 if any is listed
"""
import csv
import hashlib
import sys
from pathlib import Path

import numpy as np
from PIL import Image

BLOCKLIST = Path(__file__).resolve().parent / "photo_blocklist.tsv"
COLUMNS = ("sha1", "dhash", "licence", "title", "reason")
MAX_DISTANCE = 6


class BlockedPhoto(Exception):
    pass


def sha1_of(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def dhash_of(image):
    """64-bit difference hash: is each pixel brighter than its right neighbour, on a 9x8 grey thumbnail."""
    g = np.asarray(image.convert("L").resize((9, 8), Image.LANCZOS), np.float32)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def entry(path, licence, title, reason):
    with Image.open(path) as im:
        return {"sha1": sha1_of(path), "dhash": dhash_of(im), "licence": licence, "title": title, "reason": reason}


def read_blocklist(path=None):
    path = Path(path or BLOCKLIST)
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_blocklist(path, rows):
    unique = {r["sha1"]: {k: r[k] for k in COLUMNS} for r in rows}
    with Path(path).open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(COLUMNS)
        for r in sorted(unique.values(), key=lambda r: (r["sha1"])):
            w.writerow([r[k] for k in COLUMNS])
    _cache.pop(str(Path(path).resolve()), None)          # a list read before this write is stale


_cache = {}


def _listed(path):
    key = str(Path(path).resolve())
    if key not in _cache:
        rows = read_blocklist(path)
        _cache[key] = ({r["sha1"]: r for r in rows}, [(int(r["dhash"], 16), r) for r in rows])
    return _cache[key]


def check(photo, blocklist=None):
    """Raise BlockedPhoto if the photo, or a resized copy of it, is on the list."""
    by_sha, by_hash = _listed(blocklist or BLOCKLIST)
    hit = by_sha.get(sha1_of(photo))
    if hit is None:
        with Image.open(photo) as im:
            h = int(dhash_of(im), 16)
        hit = next((r for v, r in by_hash if bin(v ^ h).count("1") <= MAX_DISTANCE), None)
    if hit is not None:
        raise BlockedPhoto(f"{photo}: listed in the photo blocklist ({hit['licence']}, {hit['title']}: {hit['reason']})")


def drop_blocked(cams, blocklist=None):
    """{key: camera} without the cameras whose photo is listed; prints each one it drops."""
    kept = {}
    for key, cam in cams.items():
        try:
            check(cam["photo"], blocklist)
            kept[key] = cam
        except BlockedPhoto as e:
            print("dropped", key, e, flush=True)
    return kept


def open_photo(photo, blocklist=None):
    check(photo, blocklist)
    return Image.open(photo)


def main(argv):
    if argv[:1] == ["add"]:
        licence, title, reason, photos = argv[1], argv[2], argv[3], argv[4:]
        write_blocklist(BLOCKLIST, read_blocklist() + [entry(p, licence, title, reason) for p in photos])
    elif argv[:1] == ["check"]:
        bad = 0
        for p in argv[1:]:
            try:
                check(p)
            except BlockedPhoto as e:
                print(e)
                bad += 1
        sys.exit(1 if bad else 0)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
