"""make_path.py <cams.json> <key> <work_dir> <keyframes> [--fps=24]
A camera path relative to where one photo was taken, for blender_projection.py --frames. The work is done by
packages/pipeline/camera_path.py, which documents the keyframe format; this file keeps the command the notes use."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import camera_path  # noqa: E402

camera_path.main(sys.argv[1:])
