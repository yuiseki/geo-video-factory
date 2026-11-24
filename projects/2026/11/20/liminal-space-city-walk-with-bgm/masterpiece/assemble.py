"""assemble.py <plan.json> <scenes root> <work dir> <out.mp4> [--crf=18]
Puts the rendered scenes of "Tokyo, Without People" together: a title card, every scene with its place name (fades
in and out) and a small credit line (stays), crossfades between them, an end card with every credit, the BGM
(generate_ambient_bgm.py, turning to the night chords where the first scene marked "night" begins), mastered to
-14 LUFS / -1.5 dBTP in two passes.
A scene is the frames <scenes root>/<name>/<frames dir>/%04d.png (frames dir defaults to f_mac). The cards are
drawn with Pillow in Noto CJK (FONT_SERIF, FONT_SANS override the paths). Nothing is overwritten: the work dir and
the output must be new. Run it under the host's resource limits; ffmpeg inherits them.
The code lives in packages/pipeline (scene_assembly.py, title_cards.py, ambient_bgm.py), where it is tested; this
file only keeps the command line of this project working."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import scene_assembly  # noqa: E402

if __name__ == "__main__":
    sys.exit(scene_assembly.main(sys.argv[1:]))
