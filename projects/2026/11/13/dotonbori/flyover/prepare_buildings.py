#!/usr/bin/env python3
"""Prepare 3D building manifests (PLATEAU + GSI + orthophoto) for dotonbori."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
FLYOVER = Path(__file__).resolve().parent
CITY_DIR = FLYOVER / "assets/city"

EXISTING_AREAS = {
    "minami": ROOT / "projects/2026/11/17/tour-shisaibashi-dotonbori-cosmosqare/areas/minami/assets/city",
    "cosmosquare": ROOT / "projects/2026/11/17/tour-shisaibashi-dotonbori-cosmosqare/areas/cosmosquare/assets/city",
    "asakusa-ryogoku": ROOT / "projects/2026/11/17/tour-asakusa-ryogoku/assets/city",
}


def link_area(name: str, target: Path) -> None:
    if not (target / "manifest.json").is_file():
        raise FileNotFoundError(f"Missing prepared city manifest: {target / 'manifest.json'}")
    link = CITY_DIR / name
    if link.is_symlink():
        if link.resolve() == target.resolve():
            print(f"OK symlink: {name} -> {target}")
            return
        link.unlink()
    elif link.exists():
        raise FileExistsError(f"Expected symlink or absent path at {link}")
    link.symlink_to(target)
    print(f"Linked {name} -> {target}")


def prepare_shimbashi() -> None:
    area_project = FLYOVER / "assets/shimbashi_area"
    os.environ.setdefault("OVERPASS_URL", "https://overpass.yuiseki.net/api/interpreter")
    prep_path = ROOT / "projects/2026/11/17/tour-asakusa-ryogoku/prepare.py"
    spec = importlib.util.spec_from_file_location("city_preparation", prep_path)
    assert spec and spec.loader
    preparation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preparation)
    preparation.PROJECT = area_project
    preparation.BBOX = [139.750, 35.658, 139.774, 35.676]
    preparation.main()
    link_area("shimbashi", area_project / "assets/city")


def main() -> None:
    CITY_DIR.mkdir(parents=True, exist_ok=True)
    for name, target in EXISTING_AREAS.items():
        link_area(name, target)
    prepare_shimbashi()


if __name__ == "__main__":
    main()
