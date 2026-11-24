import struct
import unittest
import zlib

import numpy as np

from support import import_pipeline

seasonal_ortho = import_pipeline('geo.seasonal_ortho')


def _make_minimal_tiled_tiff(tile_offsets: list[int], tile_counts: list[int]) -> bytes:
    # Header: II, 42, ifd_offset=8
    tags = [
        (256, 4, 1, 2048),  # ImageWidth
        (257, 4, 1, 2048),  # ImageLength
        (259, 3, 1, 8),     # Compression = Deflate
        (277, 3, 1, 3),     # SamplesPerPixel = 3
        (317, 3, 1, 2),     # Predictor = 2
        (322, 4, 1, 1024),  # TileWidth
        (323, 4, 1, 1024),  # TileLength
    ]
    ifd_offset = 8
    num_tags = len(tags) + 2
    arrays_offset = ifd_offset + 2 + num_tags * 12 + 4
    off_bytes = struct.pack(f"<{len(tile_offsets)}I", *tile_offsets)
    cnt_bytes = struct.pack(f"<{len(tile_counts)}I", *tile_counts)
    tags.append((324, 4, len(tile_offsets), arrays_offset))
    tags.append((325, 4, len(tile_counts), arrays_offset + len(off_bytes)))
    tags.sort(key=lambda t: t[0])

    buf = bytearray(struct.pack("<2sHI", b"II", 42, ifd_offset))
    buf += struct.pack("<H", len(tags))
    for tag, typ, cnt, val in tags:
        buf += struct.pack("<HHII", tag, typ, cnt, val)
    buf += struct.pack("<I", 0)  # next IFD = 0
    buf += off_bytes + cnt_bytes
    return bytes(buf)


class SeasonalOrthoTests(unittest.TestCase):
    def test_decode_deflate_rgb_tile_round_trip_with_predictor(self) -> None:
        rng = np.random.default_rng(7)
        orig = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)
        diff = orig.copy()
        diff[:, 1:, :] = (orig[:, 1:, :].astype(np.int16) - orig[:, :-1, :].astype(np.int16)) & 0xFF
        compressed = zlib.compress(diff.tobytes())
        decoded = seasonal_ortho.decode_deflate_rgb_tile(compressed, tile_w=8, tile_h=8, samples=3, predictor=2)
        np.testing.assert_array_equal(decoded, orig)

    def test_parse_tiff_ifd_reads_tile_layout(self) -> None:
        hdr = _make_minimal_tiled_tiff([1000, 2000, 3000, 4000], [500, 600, 700, 800])
        info = seasonal_ortho.parse_tiff_ifd(hdr)
        self.assertEqual(info["width"], 2048)
        self.assertEqual(info["height"], 2048)
        self.assertEqual(info["tile_w"], 1024)
        self.assertEqual(info["tile_h"], 1024)
        self.assertEqual(info["compression"], 8)
        self.assertEqual(info["predictor"], 2)
        self.assertEqual(info["tile_offsets"], [1000, 2000, 3000, 4000])
        self.assertEqual(info["tile_byte_counts"], [500, 600, 700, 800])

    def test_srgb_lab_round_trip_preserves_colors(self) -> None:
        colors = np.array(
            [
                [[0, 0, 0], [255, 255, 255], [60, 150, 50], [150, 120, 80]],
            ],
            dtype=np.uint8,
        )
        lab = seasonal_ortho.srgb_to_lab(colors)
        back = seasonal_ortho.lab_to_srgb(lab)
        self.assertTrue(np.max(np.abs(back.astype(np.int16) - colors.astype(np.int16))) <= 1)

    def test_blend_seasonal_chroma_respects_mask_and_transfers_season_hue(self) -> None:
        # Brownish autumn ortho with bright/dark texture
        ortho = np.full((4, 4, 3), [130, 118, 95], dtype=np.uint8)
        ortho[0:2, :, :] = [150, 138, 110]
        # Vivid summer green season reference
        season = np.full((4, 4, 3), [55, 135, 45], dtype=np.uint8)
        # Left half masked out (roads/buildings = 0), right half vegetation (= 1)
        mask = np.zeros((4, 4), dtype=np.float32)
        mask[:, 2:] = 1.0

        out = seasonal_ortho.blend_seasonal_chroma(ortho, season, mask=mask, chroma_strength=1.0, lightness_blend=0.25)
        # Masked-out left side must match original ortho exactly
        np.testing.assert_array_equal(out[:, :2, :], ortho[:, :2, :])
        # Right side must become distinctly greener (G > R and G > B) while keeping top brighter than bottom
        self.assertGreater(int(out[0, 2, 1]), int(out[0, 2, 0]) + 15)
        self.assertGreater(int(out[0, 2, 1]), int(out[3, 2, 1]))

    def test_scene_covers_bbox_rejects_partial_footprint(self) -> None:
        bbox = (138.60, 35.20, 138.86, 35.48)
        self.assertFalse(seasonal_ortho.scene_covers_bbox({'bbox': [137.7, 34.2, 138.93, 35.225]}, bbox))
        self.assertTrue(seasonal_ortho.scene_covers_bbox({'bbox': [137.68, 35.11, 138.91, 36.12]}, bbox))
        self.assertFalse(seasonal_ortho.scene_covers_bbox({}, bbox))

    def test_blend_snow_uses_scl_and_keeps_non_snow_unchanged(self) -> None:
        base = np.full((4, 4, 3), [90, 85, 80], dtype=np.uint8)
        satellite = np.full((4, 4, 3), [235, 238, 240], dtype=np.uint8)
        scl = np.zeros((4, 4), dtype=np.uint8)
        scl[:, 2:] = 11
        out = seasonal_ortho.blend_snow(base, satellite, scl)
        np.testing.assert_array_equal(out[:, :2, :], base[:, :2, :])
        self.assertGreater(int(out[0, 3, 0]), 190)

    def test_scl_clear_ratio_excludes_cloud_and_shadow_classes(self) -> None:
        # Sentinel-2 SCL: 4=veg, 5=bare, 3=cloud shadow, 8=cloud med, 9=cloud high, 10=cirrus
        scl = np.array([[4, 4, 5, 8], [4, 9, 10, 3]], dtype=np.uint8)
        self.assertAlmostEqual(seasonal_ortho.scl_clear_ratio(scl), 0.5)


if __name__ == "__main__":
    unittest.main()
