"""Downloads shared by every project, so the same PLATEAU or GSI tile is fetched once per machine.

The root is $GEO_VIDEO_CACHE, or tmp/.cache at the top of this repository (tmp/ is not committed).

    plateau-raw/   PLATEAU 3D Tiles content exactly as served (tileset JSON, b3dm, glb), keyed by URL.
                   Independent of the box and the seed: texture resizing and PLATEAU++ work on copies.
    gsi/           GSI tiles by kind/z/x/y (building footprints, DEM, photo), as buildings.gsi_footprints
                   lays them out. An empty file records 'no tile here'.

Everything here can be fetched again, so deleting a directory only costs the download.
"""
from __future__ import annotations

import hashlib
import os
import urllib.parse
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]


def cache_root() -> Path:
    env = os.environ.get("GEO_VIDEO_CACHE")
    return Path(env) if env else REPO_ROOT / "tmp" / ".cache"


def plateau_raw_dir() -> Path:
    return cache_root() / "plateau-raw"


def gsi_dir() -> Path:
    return cache_root() / "gsi"


def cached_fetch(fetch: Callable[[str], bytes], cache_dir: Path) -> Callable[[str], bytes]:
    """fetch, but each URL's bytes are kept in cache_dir and read from there on every later call.

    Files are named by the first 20 hex digits of the URL's sha256 plus the URL path's extension,
    spread over 256 subdirectories. A failed fetch writes nothing.
    """
    cache_dir = Path(cache_dir)

    def get(url: str) -> bytes:
        digest = hashlib.sha256(url.encode()).hexdigest()[:20]
        suffix = Path(urllib.parse.urlparse(url).path).suffix
        path = cache_dir / digest[:2] / (digest + suffix)
        if path.exists():
            return path.read_bytes()
        data = fetch(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + f".{os.getpid()}.part")
        part.write_bytes(data)
        part.replace(path)
        return data

    return get
