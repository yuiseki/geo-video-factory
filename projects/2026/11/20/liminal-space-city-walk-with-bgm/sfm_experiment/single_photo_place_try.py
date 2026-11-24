"""single_photo_place_try.py <photo> <plateau tris.npz> <out_dir> <east> <north> <hfov_deg> [--radius=80] [--grid=2]
                            [--eye=1.6] [--ground=<z>] [--pitch=0:30:2] [--roll=-2:2:2] [--fov-range=0.94:1.06:3]
                            [--key=<name in cams.json>] [--mesh-radius=600] [--sky=blue|bright|dark] [--dark-below=45]
                            [--heading=<from>:<to>]
Place ONE photograph on PLATEAU with nothing but the line between the buildings and the sky. The search and the
files it writes are packages/pipeline/photo_place.py; this file keeps the command line of the experiment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
import photo_place  # noqa: E402

if __name__ == "__main__":
    photo_place.main()
