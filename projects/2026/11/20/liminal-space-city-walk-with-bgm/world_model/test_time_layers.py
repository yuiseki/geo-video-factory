import unittest

import numpy as np

import time_layers


class TimeLayers(unittest.TestCase):
    def test_brightness_reads_only_the_top_quarter(self):
        im = np.zeros((40, 10, 3), np.uint8)
        im[:10] = 255
        self.assertAlmostEqual(time_layers.sky_brightness(im), 1.0, places=3)
        im[:10], im[10:] = 0, 255
        self.assertAlmostEqual(time_layers.sky_brightness(im), 0.0, places=3)

    def test_masked_brightness_reads_the_mask_or_everything(self):
        im = np.zeros((10, 10, 3), np.uint8)
        im[:2] = 255
        mask = np.zeros((10, 10), bool)
        mask[:2] = True
        self.assertAlmostEqual(time_layers.masked_brightness(im, mask), 1.0, places=3)
        self.assertAlmostEqual(time_layers.masked_brightness(im, np.zeros((10, 10), bool)), 0.0, places=3)

    def test_layers(self):
        self.assertEqual(time_layers.layer_of(0.8), "day")
        self.assertEqual(time_layers.layer_of(0.3), "dusk")
        self.assertEqual(time_layers.layer_of(0.05), "night")


if __name__ == "__main__":
    unittest.main()
