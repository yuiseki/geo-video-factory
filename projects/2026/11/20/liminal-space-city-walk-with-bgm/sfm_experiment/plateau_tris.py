"""plateau_tris.py <pipeline_dir> <buildings_dir> <out.npz> [lon lat]
Collect all PLATEAU building triangles in one local tangent frame
(metres, x east, y north, z up from the ellipsoid) around lon/lat (default: the scramble crossing).
The work is done by packages/pipeline/buildings/plateau_mesh.py; this file keeps the command the notes use."""
import sys

sys.path.insert(0, sys.argv[1])
from buildings import plateau_mesh  # noqa: E402

plateau_mesh.main(sys.argv[2:4] + (sys.argv[4:6] if len(sys.argv) > 5 else ["139.70055", "35.65950"]))
