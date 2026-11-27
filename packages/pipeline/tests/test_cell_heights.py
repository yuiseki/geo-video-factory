"""cell_heights: the heights of filled-in buildings, calibrated per JIS third-level mesh cell on that cell's
PLATEAU buildings only, so a building's height does not depend on the box it was built in."""
import unittest

from support import import_pipeline

ch = import_pipeline("buildings.cell_heights")
jis = import_pipeline("buildings.jis_mesh")

CELL = "53394611"
W, S, E, N = jis.mesh3_bounds(CELL)


def square(lon, lat, d=0.0001):
    return {"type": "Feature", "properties": {"vt_code": "3101"},
            "geometry": {"type": "Polygon", "coordinates": [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]}}


def plateau(n, lon0, lat0, height):
    feats, heights = [], {}
    for i in range(n):
        lon, lat = lon0 + i * 0.0002, lat0
        feats.append(square(lon, lat))
        heights[f"b{lon0}-{i}"] = {"lonlat": [lon + 0.00005, lat + 0.00005], "height": height}
    return feats, heights


class CellModels(unittest.TestCase):
    def test_a_cells_model_is_its_own_buildings_whatever_lies_around(self):
        inside_f, inside_h = plateau(10, W + 0.001, S + 0.001, 30.0)
        outside_f, outside_h = plateau(10, E + 0.001, S + 0.001, 4.0)     # the next cell east
        alone = ch.cell_height_models([CELL], inside_h, inside_f)
        crowded = ch.cell_height_models([CELL], {**inside_h, **outside_h}, inside_f + outside_f)
        self.assertEqual(alone[CELL], crowded[CELL])
        area_bin = alone[CELL]["counts"]["3101"].index(10)
        self.assertEqual(alone[CELL]["heights"]["3101"][area_bin], 30.0)

    def test_model_for_picks_the_cell_of_the_point(self):
        models = {CELL: {"heights": {"3101": [1.0]}}}
        self.assertIs(ch.model_for(models)(W + 0.001, S + 0.001), models[CELL])

    def test_calibration_box_is_the_union_of_the_cells_of_the_footprints(self):
        feats = [square(W + 0.001, S + 0.001), square(E + 0.001, S + 0.001)]
        cells = ch.cells_of(feats)
        self.assertEqual(len(cells), 2)
        box = ch.cells_box(cells)
        self.assertAlmostEqual(box[0], W)
        self.assertAlmostEqual(box[2], E + jis.LON_STEP)


if __name__ == "__main__":
    unittest.main()
