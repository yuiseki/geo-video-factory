"""Atlases of the after project: the before project's photos and placements, without the photos that had no roofline.

    python projects/2026/11/26/plateau-pp-ultra-after/atlas_after.py [name ...]

For each area the before project placed photos for, work/<name>/ links its images, mesh, SfM summary and anchors,
then the before project's atlas_before.py runs world (--min-cost=0.05: photos placed at cost 0, i.e. without a
roofline, are left out; --alone: so are those whose place a site 10 m away fits as well), layers and atlas there (build_atlas writes quality.png for --atlas-fade; --people-band=2.2: street photos do not paint the lowest 2.2 m of wall). Run from the
repository root with packages/pipeline's Python, under the host's resource limits (an atlas: up to 20 GB).
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEFORE = HERE.parent / "plateau-pp-ultra-before"


def main() -> None:
    areas = [a for a in json.loads((BEFORE / "areas.json").read_text(encoding="utf-8"))["areas"] if a.get("photos")]
    names = sys.argv[1:]
    for area in areas:
        name = area["name"]
        src = BEFORE / "work" / name
        if (names and name not in names) or not (src / "anchors").exists():
            continue
        w = HERE / "work" / name
        (w / "sfm").mkdir(parents=True, exist_ok=True)
        for item in ("images", "images.json", "tris.npz", "anchors"):
            link = w / item
            if not link.exists():
                link.symlink_to(src / item)
        if not (w / "sfm" / "models.json").exists():
            (w / "sfm" / "models.json").symlink_to(src / "sfm" / "models.json")
        for step in ("world", "layers", "atlas"):
            subprocess.run([sys.executable, "-u", str(BEFORE / "atlas_before.py"), step, name, f"--root={HERE / 'work'}",
                            "--min-cost=0.05", "--alone", "--people-band=2.2"], check=True)


if __name__ == "__main__":
    main()
