#!/usr/bin/env python3
"""Prepare Zundamon & Metan sprites for the video E2E.

Uses real PSD models when MODEL_ZUNDAMON_PATH / MODEL_METAN_PATH are set,
falling back to synthetic sprites so CI and clean checkouts stay reproducible.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

FACES = ("normal", "smile", "surprise", "trouble", "point", "sad")
COLORS = {
    "zundamon": (132, 204, 110, 255),
    "metan": (228, 134, 168, 255),
}
ENV_VARS = {
    "zundamon": "MODEL_ZUNDAMON_PATH",
    "metan": "MODEL_METAN_PATH",
}


def draw_sprite(body_color: tuple[int, int, int, int], face: str, eyes: str, mouth: str) -> Image.Image:
    im = Image.new("RGBA", (180, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((24, 30, 156, 170), fill=body_color, outline=(40, 40, 40, 255), width=4)
    d.rounded_rectangle((40, 165, 140, 232), radius=18, fill=body_color, outline=(40, 40, 40, 255), width=4)
    for ex in (66, 114):
        if eyes == "c":
            d.line((ex - 12, 96, ex + 12, 96), fill=(30, 30, 30, 255), width=4)
        else:
            d.ellipse((ex - 9, 86, ex + 9, 106), fill=(30, 30, 30, 255))
    if mouth == "o":
        d.ellipse((78, 124, 102, 146), fill=(180, 60, 70, 255), outline=(30, 30, 30, 255), width=3)
    else:
        d.line((78, 134, 102, 134), fill=(30, 30, 30, 255), width=4)
    if face == "surprise":
        d.text((140, 24), "!", fill=(240, 70, 70, 255))
    elif face == "point":
        d.ellipse((142, 175, 168, 198), fill=body_color, outline=(40, 40, 40, 255), width=3)
    return im


def generate_from_psd(repo_root: Path, char_name: str, psd_path: Path, out_dir: Path) -> None:
    if not psd_path.is_file():
        raise FileNotFoundError(f"{ENV_VARS[char_name]} does not exist: {psd_path}")
    cfg_path = repo_root / ".agents/skills/geo-video-renderer/assets/template/characters" / f"{char_name}.json"
    psd_script = repo_root / "packages/pipeline/psd_sprites.py"
    shutil.rmtree(out_dir, ignore_errors=True)
    subprocess.run(
        ["uv", "run", "--with", "psd-tools", "python", str(psd_script), str(cfg_path), str(psd_path), str(out_dir)],
        check=True,
    )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare-character-zunda-metan.py WORK_PROJECT FIXTURE")
    renderer = Path(__file__).resolve().parents[2]
    repo_root = renderer.parents[1]
    project = Path(sys.argv[1]).resolve()
    fixture = renderer / "test/fixtures" / sys.argv[2]
    project.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture, project / fixture.name)

    for char_name, color in COLORS.items():
        out_dir = project / "assets" / "chara" / char_name
        model_path = os.environ.get(ENV_VARS[char_name], "").strip()
        if model_path:
            generate_from_psd(repo_root, char_name, Path(model_path).expanduser().resolve(), out_dir)
            continue
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        for face in FACES:
            for eyes in ("o", "c"):
                for mouth in ("o", "c"):
                    draw_sprite(color, face, eyes, mouth).save(out_dir / f"{face}_{eyes}_{mouth}.png")


if __name__ == "__main__":
    main()
