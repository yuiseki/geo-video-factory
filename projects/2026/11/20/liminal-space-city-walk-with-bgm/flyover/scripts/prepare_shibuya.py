#!/usr/bin/env python3
"""Prepare PLATEAU 3D Tiles for Shibuya Crossing and Center-gai."""
from __future__ import annotations

import json
from pathlib import Path
import sys

TILESET_URL = "https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13-bldg-lod2-texture-2025/tileset.json"
# Shibuya Station / Scramble Crossing / Center-gai / Dogenzaka / Jinnan
BBOX = [139.693, 35.654, 139.708, 35.666]


def cache_is_complete(manifest_path: Path) -> bool:
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    tiles = manifest.get("tiles") or []
    return bool(tiles) and all((manifest_path.parent / tile["glb"]).is_file() for tile in tiles)


def main() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    repository_dir = Path(__file__).resolve().parents[7]
    output_dir = project_dir / "assets/buildings-shibuya"
    manifest_path = output_dir / "manifest.json"
    if cache_is_complete(manifest_path):
        print(f"using cached PLATEAU models: {manifest_path}")
        return

    sys.path.insert(0, str(repository_dir / "packages/pipeline"))
    from plateau_3d import prepare_tiles

    manifest = prepare_tiles(
        TILESET_URL,
        BBOX,
        output_dir,
        max_texture_dimension=2048,
        far_texture_dimension=1024,
        workers=3,
    )
    if not manifest.get("tiles"):
        raise RuntimeError("PLATEAU preparation produced no building tiles")
    print(f"prepared {manifest['tile_count']} PLATEAU tiles in {output_dir}")


if __name__ == "__main__":
    main()
