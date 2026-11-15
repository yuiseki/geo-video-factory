#!/usr/bin/env python3
"""Create and cache Fuji seasonal imagery for the video E2E."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image


def feather_alpha(width: int, height: int) -> np.ndarray:
    """Fade the edge of the seasonal mosaic into the underlying GSI tiles."""
    x = np.minimum(np.arange(width), np.arange(width)[::-1]) / max(width * 0.12, 1)
    y = np.minimum(np.arange(height), np.arange(height)[::-1]) / max(height * 0.12, 1)
    return np.rint(np.clip(np.minimum(y[:, None], x[None, :]), 0, 1) * 255).astype(np.uint8)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit('usage: prepare-fuji-seasonal.py WORK_PROJECT FIXTURE')
    renderer = Path(__file__).resolve().parents[2]
    project = Path(sys.argv[1]).resolve()
    fixture = renderer / 'test/fixtures' / sys.argv[2]
    output = project / 'fuji-seasons'
    manifest = output / 'manifest.json'
    seasons = ('summer', 'autumn', 'winter', 'spring')
    if not manifest.is_file() or not all((output / f'{name}.jpg').is_file() for name in seasons):
        sys.path.insert(0, str(renderer.parents[1] / 'packages/pipeline'))
        import seasonal_ortho
        seasonal_ortho.main([
            '--bbox', '138.61,35.24,138.86,35.48', '--zoom', '12', '--out-dir', str(output),
            '--season', 'summer=2024-07-15T00:00:00Z/2024-08-31T23:59:59Z',
            '--season', 'autumn=2023-10-15T00:00:00Z/2023-11-30T23:59:59Z',
            '--season', 'winter=2024-01-01T00:00:00Z/2024-02-29T23:59:59Z',
            '--season', 'spring=2024-04-01T00:00:00Z/2024-05-31T23:59:59Z',
        ])
    for name in seasons:
        source = output / f'{name}.jpg'
        target = output / f'{name}.png'
        if not target.is_file() or target.stat().st_mtime < source.stat().st_mtime:
            with Image.open(source) as image:
                rgba = image.convert('RGBA')
                rgba.putalpha(Image.fromarray(feather_alpha(*rgba.size)))
                rgba.save(target)
    data = json.loads(manifest.read_text(encoding='utf-8'))
    spec = json.loads(fixture.read_text(encoding='utf-8'))
    for shot in spec['shots']:
        for overlay in shot.get('overlays', []):
            if overlay.get('type') == 'image':
                overlay['bbox'] = data['bounds']
    project.mkdir(parents=True, exist_ok=True)
    (project / fixture.name).write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
