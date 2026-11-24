import unittest

import ground_ortho as go


class Tiles(unittest.TestCase):
    def test_tile_and_back(self):
        x, y = go.tile_of(139.7005, 35.6595, 18)
        lon, lat = go.lonlat_of(x, y, 18)
        self.assertAlmostEqual(lon, 139.7005, places=9)
        self.assertAlmostEqual(lat, 35.6595, places=9)

    def test_north_is_smaller_y(self):
        self.assertLess(go.tile_of(139.7, 35.67, 18)[1], go.tile_of(139.7, 35.66, 18)[1])


if __name__ == "__main__":
    unittest.main()
