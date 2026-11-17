#!/usr/bin/env python3
"""Prepare cached 3D city & seasonal assets for plateau-award-2026 via symlinks."""
from __future__ import annotations

from pathlib import Path

PROJECT = Path(__file__).resolve().parent
REPO = PROJECT.parents[4]
ASSETS = PROJECT / "assets"

LINKS = {
    "shinjuku-sota": REPO / "packages/renderer/dist/test/video/.work/buildings-tokyo-sota/project/assets/buildings-tokyo-sota/shinjuku-sota",
    "sota": REPO / "packages/renderer/dist/test/video/.work/buildings-tokyo-sota/project/assets/buildings-tokyo-sota/sota",
    "buildings-asakusa": REPO / "packages/renderer/dist/test/video/.work/buildings-asakusa-sumida-river/project/assets/buildings-asakusa",
    "asakusa-sota": REPO / "projects/2026/11/17/tour-asakusa-ryogoku/assets/city",
    "omuro-seasons": REPO / "packages/renderer/test/fixtures/omuro-seasons",
    "osaka-cosmosquare": REPO / "projects/2026/11/17/tour-shisaibashi-dotonbori-cosmosqare/areas/cosmosquare/assets/city",
    "osaka-minami": REPO / "projects/2026/11/17/tour-shisaibashi-dotonbori-cosmosqare/areas/minami/assets/city",
    "hakodate": REPO / "projects/2026/11/17/hakodate-terrain-buildings/assets/city",
}


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    missing = []
    for name, target in LINKS.items():
        link = ASSETS / name
        if link.is_symlink() or link.exists():
            if link.is_symlink() and link.resolve() != target.resolve():
                link.unlink()
            else:
                status = "OK" if target.exists() else "MISSING_TARGET"
                print(f"  {name}: {status} -> {target}")
                if not target.exists():
                    missing.append((name, target))
                continue
        if not target.exists():
            missing.append((name, target))
        link.symlink_to(target)
        print(f"  {name}: linked -> {target}")
    if missing:
        print("\nWARNING: Some targets do not exist yet:")
        for name, target in missing:
            print(f"  - {name}: {target}")


if __name__ == "__main__":
    main()
