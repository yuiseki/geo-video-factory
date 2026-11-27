"""photo_place on photos solved from the photo alone: the search may get faster, the place it finds may not move.

The frozen numbers are what the full search (every place on a 2 m grid) found before it was made faster."""
import json
import unittest
from pathlib import Path

import numpy as np

from support import import_pipeline

pp = import_pipeline("geo.photo_place")
pe = import_pipeline("photos.photo_exif")
pb = import_pipeline("buildings.plateau_building")
ps = import_pipeline("geo.photo_solve")

PHOTOS = Path(__file__).resolve().parents[1] / "camera_truth" / "photos"
FROZEN = {
    # Ueno-Okachimachi, Redmi 12 5G, GPS by network: full 2 m search, blue sky
    "ueno_okachimachi_20261127_1019.jpg": {
        "sky": "blue", "best": {"east": -5.5, "north": -17.0, "heading": 61.0, "pitch": 21.0, "hfov": 60.8}},
    # Shibuya, Xiaomi M2101K9R, no 35 mm equivalent, GPS marked CELLID: full 300 m search, overcast (bright) sky
    "shibuya_20230321_1432.jpg": {
        "sky": "bright", "best": {"east": 1.5, "north": -2.0, "heading": 292.5, "pitch": 18.5, "hfov": 55.0}},
}


def ready():
    try:
        from buildings.pp_tiles import store
        return any(store().glob("plateau/*/*.json"))
    except Exception:
        return False


@unittest.skipUnless(ready(), "no PLATEAU++ tile store here")
class Frozen(unittest.TestCase):
    def test_the_search_photo_solve_runs_finds_the_frozen_place(self):
        import tempfile
        for name, frozen in FROZEN.items():
            with self.subTest(photo=name):
                photo = PHOTOS / name
                ex = pe.camera_from_exif(photo)
                work = Path(tempfile.mkdtemp())
                t = pb.area_triangles((ex["lon"], ex["lat"]), (0.0, 0.0), 700.0)
                np.savez_compressed(work / "tris.npz", tris=t.astype(np.float32))
                import time
                t0 = time.time()
                got = ps.step_place(photo, work / "tris.npz", ex, frozen["sky"], work)
                print(name, f"{time.time() - t0:.0f} s, radius {got.get('radius')}", flush=True)
                self.assertLess(time.time() - t0, 300)             # it took 15 minutes once
                b, f = got["best"], frozen["best"]
                self.assertTrue(got["alone"])
                self.assertLess(np.hypot(b["east"] - f["east"], b["north"] - f["north"]), 1.5)
                self.assertLess(abs((b["heading"] - f["heading"] + 180) % 360 - 180), 1.5)
                self.assertLess(abs(b["pitch"] - f["pitch"]), 1.5)


if __name__ == "__main__":
    unittest.main()
