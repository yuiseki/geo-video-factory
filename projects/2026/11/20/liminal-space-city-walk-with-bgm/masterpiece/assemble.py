"""assemble.py <plan_vN.json> <out.mp4> [--work <dir>] [--bgm <wav>] [--dry-run]

Assemble a Shibuya photo-walk masterpiece video from a plan JSON. The work is
done by packages/pipeline/video/scene_assembly.py; this file only keeps the
command line of this project working."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
from video import scene_assembly  # noqa: E402

if __name__ == "__main__":
    sys.exit(scene_assembly.main(sys.argv[1:]))
