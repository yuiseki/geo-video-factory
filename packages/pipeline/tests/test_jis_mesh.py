"""jis_mesh: JIS X 0410 third-level mesh (about 1 km), the fixed cells PLATEAU++ calibrates heights in."""
import unittest

from support import import_pipeline

jis = import_pipeline("buildings.jis_mesh")


class Mesh(unittest.TestCase):
    def test_tokyo_station_is_in_53394611(self):
        self.assertEqual(jis.mesh3(139.7671, 35.6812), "53394611")

    def test_a_cell_holds_its_own_corner_and_not_its_far_edge(self):
        w, s, e, n = jis.mesh3_bounds("53394611")
        self.assertAlmostEqual(e - w, 45 / 3600)
        self.assertAlmostEqual(n - s, 30 / 3600)
        self.assertEqual(jis.mesh3(w + 1e-9, s + 1e-9), "53394611")
        self.assertNotEqual(jis.mesh3(e + 1e-9, s + 1e-9), "53394611")
        self.assertTrue(w <= 139.7671 < e and s <= 35.6812 < n)

    def test_the_cells_of_a_box_cover_it_and_only_touch_it(self):
        box = [139.765, 35.680, 139.780, 35.690]
        cells = jis.mesh3_cells(box)
        self.assertEqual(cells, sorted(set(cells)))
        for code in cells:
            w, s, e, n = jis.mesh3_bounds(code)
            self.assertTrue(w < box[2] and e > box[0] and s < box[3] and n > box[1])
        for lon in (139.765, 139.772, 139.7799):
            for lat in (35.680, 35.685, 35.6899):
                self.assertIn(jis.mesh3(lon, lat), cells)

    def test_cells_cross_a_first_level_boundary(self):
        self.assertEqual(jis.mesh3(139.9999, 35.70), jis.mesh3(139.9999, 35.70))
        self.assertNotEqual(jis.mesh3(139.9999, 35.70)[2:4], jis.mesh3(140.0001, 35.70)[2:4])


if __name__ == "__main__":
    unittest.main()
