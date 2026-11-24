#!/usr/bin/env python3
"""Prepare the real PLATEAU cache used by the buildings-asakusa video E2E."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys


TILESET_URL = "https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13-bldg-lod2-texture-2025/tileset.json"
BBOX = [139.776, 35.689, 139.811, 35.720]


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
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare-buildings-asakusa.py WORK_PROJECT FIXTURE")

    renderer_dir = Path(__file__).resolve().parents[2]
    repository_dir = renderer_dir.parents[1]
    project_dir = Path(sys.argv[1]).resolve()
    fixture = renderer_dir / "test/fixtures" / sys.argv[2]
    project_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture, project_dir / fixture.name)

    output_dir = project_dir / "assets/buildings-asakusa"
    manifest_path = output_dir / "manifest.json"
    if cache_is_complete(manifest_path):
        print(f"using cached PLATEAU models: {manifest_path}")
        return

    sys.path.insert(0, str(repository_dir / "packages/pipeline"))
    from buildings.plateau_3d import prepare_tiles

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
