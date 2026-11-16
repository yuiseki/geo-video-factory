#!/usr/bin/env python3
"""Prepare Yukkuri reaction sprites for the video E2E.

Uses real part directories when MODEL_REIMU_PATH / MODEL_MARISA_PATH are set,
falling back to synthetic layered parts so CI and clean checkouts stay reproducible.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ENV_VARS = {
    "reimu": "MODEL_REIMU_PATH",
    "marisa": "MODEL_MARISA_PATH",
}


def _save_part(path: Path, draw_fn) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(im))
    im.save(path)


def _create_parts(parts_dir: Path, hair_color: tuple[int, int, int, int], acc_color: tuple[int, int, int, int]) -> dict:
    _save_part(parts_dir / "体" / "体_00.png", lambda d: d.ellipse((45, 50, 175, 180), fill=(255, 238, 224, 255), outline=(40, 30, 30, 255), width=4))
    _save_part(parts_dir / "髪" / "髪_00.png", lambda d: d.arc((35, 35, 185, 165), 180, 360, fill=hair_color, width=18))
    _save_part(parts_dir / "他" / "服_01.png", lambda d: d.polygon([(70, 38), (110, 18), (150, 38)], fill=acc_color, outline=(40, 30, 30, 255)))
    _save_part(parts_dir / "顔色" / "顔_00.png", lambda d: d.ellipse((62, 120, 82, 132), fill=(255, 160, 160, 160)))
    _save_part(parts_dir / "眉" / "眉_00.png", lambda d: (d.line((72, 85, 96, 85), fill=(40, 30, 30, 255), width=4), d.line((124, 85, 148, 85), fill=(40, 30, 30, 255), width=4)))
    _save_part(parts_dir / "目" / "目_00.png", lambda d: (d.ellipse((76, 94, 92, 114), fill=(40, 30, 30, 255)), d.ellipse((128, 94, 144, 114), fill=(40, 30, 30, 255))))
    _save_part(parts_dir / "目" / "目_00.0.png", lambda d: (d.line((74, 104, 94, 104), fill=(40, 30, 30, 255), width=4), d.line((126, 104, 146, 104), fill=(40, 30, 30, 255), width=4)))
    _save_part(parts_dir / "口" / "口_00.1.png", lambda d: d.line((100, 140, 120, 140), fill=(40, 30, 30, 255), width=4))
    _save_part(parts_dir / "口" / "口_00.4.png", lambda d: d.ellipse((100, 132, 120, 150), fill=(190, 60, 70, 255), outline=(40, 30, 30, 255), width=3))
    return {
        "order": ["体", "顔色", "口", "目", "髪", "眉", "他"],
        "width": 200,
        "min_width": 160,
        "base": {"体": "体_00", "髪": "髪_00", "他": "服_01", "顔色": "顔_00", "眉": "眉_00", "目": "目_00"},
        "blink": {"目": "目_00.0"},
        "faces": {
            "normal": {"mouth_open": "口_00.4", "mouth_closed": "口_00.1"},
            "smile": {"mouth_open": "口_00.4", "mouth_closed": "口_00.1"},
            "point": {"mouth_open": "口_00.4", "mouth_closed": "口_00.1"},
        },
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare-character-yukkuri.py WORK_PROJECT FIXTURE")
    renderer = Path(__file__).resolve().parents[2]
    repo_root = renderer.parents[1]
    project = Path(sys.argv[1]).resolve()
    fixture = renderer / "test/fixtures" / sys.argv[2]
    project.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture, project / fixture.name)

    sys.path.insert(0, str(repo_root / "packages/pipeline"))
    import part_sprites

    configs = {
        "reimu": ((45, 30, 30, 255), (210, 40, 50, 255)),
        "marisa": ((240, 200, 70, 255), (40, 40, 55, 255)),
    }
    char_templates = repo_root / ".agents/skills/geo-video-renderer/assets/template/characters"
    for name, (hair, acc) in configs.items():
        out_dir = project / "assets" / "chara" / name
        shutil.rmtree(out_dir, ignore_errors=True)
        model_path = os.environ.get(ENV_VARS[name], "").strip()
        if model_path:
            parts_dir = Path(model_path).expanduser().resolve()
            if not parts_dir.is_dir():
                raise FileNotFoundError(f"{ENV_VARS[name]} does not exist: {parts_dir}")
            cfg = json.loads((char_templates / f"{name}.json").read_text(encoding="utf-8"))
            part_sprites.render(parts_dir, cfg, out_dir)
            continue
        parts_dir = project / "_parts" / name
        cfg = _create_parts(parts_dir, hair, acc)
        part_sprites.render(parts_dir, cfg, out_dir)


if __name__ == "__main__":
    main()
