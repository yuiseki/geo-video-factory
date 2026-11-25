#!/usr/bin/env python3
"""PLATEAU++ for the Shibuya descent: every building the camera can see, with a texture.

    prepare_shibuya_plateau_pp.py <out dir> [--bbox=w,s,e,n] [--cache=dir]

The steps, including taking out buildings that cannot be real, are packages/pipeline/buildings/plateau_pp.py;
this only gives them Shibuya's box and seed. Needs packages/pipeline/requirements-dev.txt and OVERPASS_URL set
to your own Overpass instance. Run under the host's resource limits."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[7]
sys.path.insert(0, str(REPO / "packages/pipeline"))
from buildings import plateau_pp  # noqa: E402

# the zoom-14 view at the start of the descent: every building the camera frames (pp-v2 and later)
BBOX = [139.6706, 35.6458, 139.7306, 35.6728]
SEED = "shibuya-plateau-pp-v1"


def main(argv: list[str]) -> None:
    opts = dict(a[2:].split("=", 1) for a in argv if a.startswith("--"))
    out = Path([a for a in argv if not a.startswith("--")][0]).resolve()
    bbox = [float(v) for v in opts["bbox"].split(",")] if "bbox" in opts else BBOX
    plateau_pp.build(out, bbox, plateau_pp.TOKYO_2025, Path(opts["cache"]).resolve() if "cache" in opts else None, SEED)


if __name__ == "__main__":
    main(sys.argv[1:])
