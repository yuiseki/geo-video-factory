"""Compose reaction-wipe sprites from layered PNG part directories.

Supports folder-based part collections (e.g., Tanuki-style Yukkuri sprites)
and writes <outdir>/<face>_<eyes o|c>_<mouth o|c>.png plus sheet.png,
matching the sprite layout expected by the renderer's reaction overlay.

Usage:
  python3 packages/pipeline/part_sprites.py <character.json> <parts_dir> <outdir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

DEFAULT_ORDER = ("体", "顔色", "口", "目", "髪", "眉", "他")


def resolve_part_path(parts_dir: Path, category: str, part_name: str) -> Path:
    """Resolve a part PNG path inside <parts_dir>/<category>/<part_name>."""
    filename = part_name if part_name.endswith(".png") else f"{part_name}.png"
    candidate = parts_dir / category / filename
    if not candidate.is_file():
        raise FileNotFoundError(f"part PNG not found: {candidate}")
    return candidate


def _load_rgba(path: Path, cache: dict[Path, Image.Image]) -> Image.Image:
    if path not in cache:
        with Image.open(path) as im:
            cache[path] = im.convert("RGBA")
    return cache[path]


def compose_layers(
    parts_dir: Path,
    order: list[str] | tuple[str, ...],
    selection: dict[str, str],
    cache: dict[Path, Image.Image],
) -> Image.Image:
    """Alpha-composite selected parts in bottom-to-top layer order."""
    canvas: Image.Image | None = None
    for category in order:
        part_name = selection.get(category)
        if not part_name:
            continue
        layer = _load_rgba(resolve_part_path(parts_dir, category, part_name), cache)
        if canvas is None:
            canvas = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        canvas.alpha_composite(layer)
    if canvas is None:
        raise ValueError("no parts selected to compose")
    return canvas


def _union_bbox(images: list[tuple[str, Image.Image]], pad: int = 4) -> tuple[int, int, int, int]:
    boxes = [im.getbbox() for _, im in images]
    valid = [b for b in boxes if b is not None]
    if not valid:
        w, h = images[0][1].size
        return (0, 0, w, h)
    w, h = images[0][1].size
    return (
        max(0, min(b[0] for b in valid) - pad),
        max(0, min(b[1] for b in valid) - pad),
        min(w, max(b[2] for b in valid) + pad),
        min(h, max(b[3] for b in valid) + pad),
    )


def _anchor_corners(im: Image.Image) -> Image.Image:
    """Place alpha=1 pixels on transparent corners to prevent trimming drift."""
    w, h = im.size
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if im.getpixel(xy)[3] == 0:
            im.putpixel(xy, (0, 0, 0, 1))
    return im


def render(parts_dir: str | Path, cfg: dict, outdir: str | Path) -> list[str]:
    """Render all face/eye/mouth combinations and a 4-column contact sheet."""
    faces = cfg.get("faces")
    if not faces:
        raise ValueError('character config must define at least one face under "faces"')

    parts_root = Path(parts_dir)
    out_root = Path(outdir)
    out_root.mkdir(parents=True, exist_ok=True)

    order = cfg.get("order") or list(DEFAULT_ORDER)
    width = int(cfg.get("width", 360))
    min_width = int(cfg.get("min_width", 0))
    mouth_cat = cfg.get("mouth_category", "口")
    cache: dict[Path, Image.Image] = {}

    raw: list[tuple[str, Image.Image]] = []
    for face, f_cfg in faces.items():
        for eyes in ("o", "c"):
            for mouth in ("o", "c"):
                selection = dict(cfg.get("base", {}))
                selection.update(f_cfg.get("select", {}))
                selection[mouth_cat] = f_cfg["mouth_open"] if mouth == "o" else f_cfg["mouth_closed"]
                if eyes == "c":
                    blink = f_cfg.get("blink", cfg.get("blink", {}))
                    selection.update(blink)
                im = compose_layers(parts_root, order, selection, cache)
                raw.append((f"{face}_{eyes}_{mouth}.png", im))

    bbox = _union_bbox(raw)
    made: list[tuple[str, Image.Image]] = []
    for name, im in raw:
        cropped = im.crop(bbox)
        if min_width > cropped.width:
            padded = Image.new("RGBA", (min_width, cropped.height), (0, 0, 0, 0))
            padded.alpha_composite(cropped, ((min_width - cropped.width) // 2, 0))
            cropped = padded
        target_h = max(1, round(width * cropped.height / cropped.width))
        resized = _anchor_corners(cropped.resize((width, target_h), Image.LANCZOS))
        resized.save(out_root / name)
        made.append((name, resized))

    cols = 4
    w, h = made[0][1].size
    rows = (len(made) + cols - 1) // cols
    sheet = Image.new("RGBA", (w * cols, h * rows), (60, 60, 70, 255))
    for i, (_, im) in enumerate(made):
        sheet.alpha_composite(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(out_root / "sheet.png")
    return [name for name, _ in made]


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: part_sprites.py <character.json> <parts_dir> <outdir>")
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for filename in render(sys.argv[2], config, sys.argv[3]):
        print(filename)
