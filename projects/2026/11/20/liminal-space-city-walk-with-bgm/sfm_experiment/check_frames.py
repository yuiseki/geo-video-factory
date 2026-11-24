"""check_frames.py <frames dir> [min mean 0-255]   Exit 1 and list the frames that are darker than the limit.
The work is done by packages/pipeline/frame_check.py; this file keeps the command the notes use."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import frame_check  # noqa: E402

sys.exit(frame_check.main(sys.argv[1:]))
