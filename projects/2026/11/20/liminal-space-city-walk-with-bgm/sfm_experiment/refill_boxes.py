"""refill_boxes.py <photo> <out png> <work dir> <pipeline dir> <lama model> <x0,y0,x1,y1> ...
Fill hand-drawn boxes (pixels of the photo: people the detector missed) with LaMa, each inside its own crop, and
paste the crops back. The work is done by `people_removal.py refill` in packages/pipeline; this file keeps the
command the notes use, including the pipeline directory as an argument (it runs in the environment that has
torch, where the repository may sit elsewhere)."""
import sys

sys.path.insert(0, sys.argv[4])
from photos import people_removal as pr  # noqa: E402

pr.refill_boxes(sys.argv[5], sys.argv[1], sys.argv[2], sys.argv[3], [pr.parse_box(a) for a in sys.argv[6:]])
