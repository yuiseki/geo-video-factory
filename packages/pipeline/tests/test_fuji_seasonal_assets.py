import importlib.util
from pathlib import Path
import unittest

import numpy as np

SCRIPT = Path(__file__).resolve().parents[2] / 'renderer/test/e2e/prepare-fuji-seasonal.py'
spec = importlib.util.spec_from_file_location('prepare_fuji_seasonal', SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FujiSeasonalAssetTests(unittest.TestCase):
    def test_feather_leaves_center_opaque_and_edges_transparent(self) -> None:
        alpha = module.feather_alpha(100, 80)
        self.assertEqual(alpha.shape, (80, 100))
        self.assertEqual(int(alpha[0, 50]), 0)
        self.assertEqual(int(alpha[40, 0]), 0)
        self.assertEqual(int(alpha[40, 50]), 255)
        self.assertGreater(int(alpha[4, 50]), 0)
        self.assertLess(int(alpha[4, 50]), 255)


if __name__ == '__main__':
    unittest.main()
