"""generate_ambient_bgm.py <out.wav> <seconds> [--night-from=<s>] [--seed=7]
A calm ambient piece for "Tokyo, Without People", synthesized from sines and noise only: nothing is sampled,
so there is no licence to clear. D major, four chords of 8 s (60 BPM, two bars each): soft pads, a sub bass, sparse
bell notes on the pentatonic scale with an echo, a breath of filtered noise, and one long reverb.
With --night-from the chords turn to B minor from that second on (rounded to a chord boundary), the bells drop an
octave and thin out. The piece fades in over 3 s and out over 7 s. 48 kHz, 16 bit, stereo; the loudness is left
to the mastering step (ffmpeg loudnorm).
The code lives in packages/pipeline/narration/ambient_bgm.py, where it is tested; this file only keeps the command line of
this project working."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
from narration import ambient_bgm  # noqa: E402

if __name__ == "__main__":
    sys.exit(ambient_bgm.main(sys.argv[1:]))
