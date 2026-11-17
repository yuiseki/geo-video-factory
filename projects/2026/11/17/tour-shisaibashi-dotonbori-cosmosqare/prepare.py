#!/usr/bin/env python3
"""Prepare two Osaka areas using the shared Asakusa SOTA preparation workflow."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
PROJECT = Path(__file__).resolve().parent
TILESET = 'https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/27100-bldg-maxlod2-2025/tileset.json'
AREAS = {
    'minami': [135.492, 34.664, 135.513, 34.680],
    'cosmosquare': [135.403, 34.635, 135.424, 34.650],
}


def main() -> None:
    selected = sys.argv[1:] or list(AREAS)
    unknown = set(selected) - set(AREAS)
    if unknown:
        raise SystemExit(f'Unknown areas: {sorted(unknown)}')
    path = ROOT / 'projects/2026/11/17/tour-asakusa-ryogoku/prepare.py'
    spec = importlib.util.spec_from_file_location('city_preparation', path)
    assert spec and spec.loader
    preparation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preparation)
    preparation.TILESET = TILESET
    for area in selected:
        print(f'Preparing {area}: {AREAS[area]}', flush=True)
        preparation.PROJECT = PROJECT / 'areas' / area
        preparation.BBOX = AREAS[area]
        preparation.main()


if __name__ == '__main__':
    main()
