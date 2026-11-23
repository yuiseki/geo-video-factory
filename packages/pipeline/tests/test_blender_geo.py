import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blender_geo as bg  # noqa: E402


def _apply(matrix, point):
    x, y, z = point
    return tuple(matrix[r][0] * x + matrix[r][1] * y + matrix[r][2] * z + matrix[r][3] for r in range(3))


class MapLibreCameraTests(unittest.TestCase):
    def test_meters_per_pixel_matches_maplibre_512px_tiles(self):
        # 2 * pi * 6378137 * cos(lat) / (512 * 2 ** zoom)
        self.assertAlmostEqual(bg.meters_per_pixel(0, 0), 78271.517, places=2)
        self.assertAlmostEqual(bg.meters_per_pixel(20, 60), 0.0373, places=4)

    def test_camera_sits_behind_the_center_along_the_bearing(self):
        cam = bg.maplibre_camera(
            center=[139.70058, 35.65928], zoom=19.75, pitch=84, bearing=-26,
            fov=82, height_px=720, origin=[139.70058, 35.65928],
        )
        distance = 0.5 * 720 / math.tan(math.radians(41)) * bg.meters_per_pixel(19.75, 35.65928)
        self.assertAlmostEqual(cam["distance"], distance, places=6)
        x, y, z = cam["location"]
        self.assertAlmostEqual(z, distance * math.cos(math.radians(84)), places=6)
        horizontal = distance * math.sin(math.radians(84))
        self.assertAlmostEqual(x, -horizontal * math.sin(math.radians(-26)), places=6)
        self.assertAlmostEqual(y, -horizontal * math.cos(math.radians(-26)), places=6)
        self.assertTrue(2.5 < z < 4.0, z)  # eye height of v31

    def test_camera_rotation_looks_at_the_center(self):
        cam = bg.maplibre_camera(
            center=[139.70, 35.66], zoom=19, pitch=60, bearing=120,
            fov=40, height_px=720, origin=[139.70, 35.66],
        )
        rx, ry, rz = cam["rotation_euler"]
        self.assertAlmostEqual(rx, math.radians(60))
        self.assertAlmostEqual(ry, 0)
        self.assertAlmostEqual(rz, math.radians(-120))
        # Blender camera looks down local -Z; apply Rz(rz) * Rx(rx) to (0, 0, -1).
        dx, dy, dz = 0.0, math.sin(rx), -math.cos(rx)
        wx = dx * math.cos(rz) - dy * math.sin(rz)
        wy = dx * math.sin(rz) + dy * math.cos(rz)
        lx, ly, lz = cam["location"]
        t = -lz / dz
        self.assertAlmostEqual(lx + wx * t, 0, places=6)
        self.assertAlmostEqual(ly + wy * t, 0, places=6)
        self.assertAlmostEqual(cam["fov_vertical"], math.radians(40))

    def test_interpolates_shot_keys_linearly(self):
        keys = [
            {"t": 0, "center": [139.0, 35.0], "zoom": 19, "pitch": 80, "bearing": -30},
            {"t": 1, "center": [139.2, 35.2], "zoom": 20, "pitch": 84, "bearing": -26},
        ]
        mid = bg.interpolate_keys(keys, 0.5)
        self.assertAlmostEqual(mid["center"][0], 139.1)
        self.assertAlmostEqual(mid["zoom"], 19.5)
        self.assertAlmostEqual(mid["pitch"], 82)
        self.assertAlmostEqual(mid["bearing"], -28)
        self.assertEqual(bg.interpolate_keys(keys, 2)["zoom"], 20)


class PlacementTests(unittest.TestCase):
    def test_local_meters_matches_the_renderer(self):
        x, y = bg.local_meters([139.701, 35.661], [139.700, 35.660])
        self.assertAlmostEqual(x, 0.001 * 111_320 * math.cos(math.radians(35.660)), places=6)
        self.assertAlmostEqual(y, 0.001 * 110_950, places=6)

    def test_tile_matrix_maps_blender_import_coords_to_local_enu(self):
        center = [139.7005, 35.66]
        rtc = bg.wgs84_ecef([139.7005, 35.66, 0])
        matrix = bg.plateau_tile_matrix(rtc, center, height_offset=-54)
        # The glTF importer turns Y-up (x, y, z) into Blender (x, -z, y), which equals the ECEF offset.
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(_apply(matrix, (0, 0, 0)), (0, 0, -54))))
        up = bg.wgs84_ecef([139.7005, 35.66, 10])
        offset = tuple(u - r for u, r in zip(up, rtc))
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(_apply(matrix, offset), (0, 0, -44))))

    def test_tile_matrix_puts_an_eastern_point_on_positive_x(self):
        center = [139.7005, 35.66]
        rtc = bg.wgs84_ecef([139.7015, 35.66, 0])
        x, y, z = _apply(bg.plateau_tile_matrix(rtc, center), (0, 0, 0))
        self.assertAlmostEqual(x, 0.001 * 111_320 * math.cos(math.radians(35.66)), delta=0.2)
        self.assertAlmostEqual(y, 0, delta=0.05)
        self.assertLess(abs(z), 0.05)

    def test_facing_bearing_rotates_a_plane_to_face_the_azimuth(self):
        # A plane whose front faces -Y after the X rotation faces the given azimuth after the Z rotation.
        for bearing in (0, 90, 156, 282):
            rx, ry, rz = bg.facing_euler(bearing)
            nx, ny = 0.0, -1.0  # normal after Rx(90deg) of +Z
            self.assertAlmostEqual(rx, math.pi / 2)
            fx = nx * math.cos(rz) - ny * math.sin(rz)
            fy = nx * math.sin(rz) + ny * math.cos(rz)
            self.assertAlmostEqual(fx, math.sin(math.radians(bearing)), places=9)
            self.assertAlmostEqual(fy, math.cos(math.radians(bearing)), places=9)


class StrictGlbTests(unittest.TestCase):
    def _glb(self, document, binary=b"\x01\x02\x03\x04"):
        import json
        import struct

        raw = json.dumps(document).encode()
        raw += b" " * ((-len(raw)) % 4)
        total = 12 + 8 + len(raw) + 8 + len(binary)
        return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(raw), b"JSON") + raw
                + struct.pack("<I4s", len(binary), b"BIN\0") + binary)

    def test_drops_cesium_rtc_from_required_and_keeps_the_binary_chunk(self):
        import json
        import struct

        payload = self._glb({"extensionsUsed": ["KHR_draco_mesh_compression"],
                             "extensionsRequired": ["CESIUM_RTC", "KHR_draco_mesh_compression"]})
        fixed = bg.strict_glb(payload)
        _, _, total = struct.unpack_from("<4sII", fixed)
        self.assertEqual(total, len(fixed))
        length = struct.unpack_from("<I", fixed, 12)[0]
        document = json.loads(fixed[20:20 + length])
        self.assertEqual(document["extensionsRequired"], ["KHR_draco_mesh_compression"])
        self.assertTrue(fixed.endswith(b"BIN\0\x01\x02\x03\x04"))
        self.assertEqual(length % 4, 0)

    def test_leaves_clean_files_untouched_and_rejects_non_glb(self):
        payload = self._glb({"asset": {"version": "2.0"}})
        self.assertIs(bg.strict_glb(payload), payload)
        with self.assertRaises(ValueError):
            bg.strict_glb(b"not a glb at all, really")


if __name__ == "__main__":
    unittest.main()
