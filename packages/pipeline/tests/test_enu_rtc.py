"""enu_rtc: a filled-in tile written in local east/up/south metres around its own centre becomes a tile in ECEF
offsets from an RTC centre, like PLATEAU's, so every consumer places it the same way and no box centre is needed."""
import json
import math
import struct
import unittest

import numpy as np

from support import import_pipeline

er = import_pipeline("buildings.enu_rtc")
gs = import_pipeline("buildings.glb_spatial")
p3 = import_pipeline("buildings.plateau_3d")

LON0, LAT0, GEOID = 139.79, 35.71, 36.7


def glb(points, normals):
    pos = np.asarray(points, np.float32).tobytes()
    nor = np.asarray(normals, np.float32).tobytes()
    binary = pos + nor
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos)},
                           {"buffer": 0, "byteOffset": len(pos), "byteLength": len(nor)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(points), "type": "VEC3",
                          "min": [0, 0, 0], "max": [0, 0, 0]},
                         {"bufferView": 1, "componentType": 5126, "count": len(points), "type": "VEC3"}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}}]}],
           "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}]}
    j = json.dumps(doc).encode()
    j += b" " * (-len(j) % 4)
    total = 12 + 8 + len(j) + 8 + len(binary)
    return struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(j), b"JSON") + j + \
        struct.pack("<I4s", len(binary), b"BIN\0") + binary


class ToRtc(unittest.TestCase):
    def test_a_point_lands_where_the_local_metres_say_on_the_ellipsoid(self):
        # 100 m east, 50 m north (z = -50), 20 m above the geoid
        out, rtc = er.to_rtc(glb([[100, 20, -50]], [[0, 1, 0]]), LON0, LAT0, GEOID)
        doc, binary, _ = p3.glb_chunks(out)
        x, y, z = np.frombuffer(binary[:12], np.float32)
        ecef = np.array(rtc) + np.array([x, -z, y])
        east = 100 / (111_320 * math.cos(math.radians(LAT0)))
        want = np.array(gs._ecef(LON0 + east, LAT0 + 50 / 110_950, 20 + GEOID))
        self.assertLess(np.linalg.norm(ecef - want), 0.5)
        self.assertEqual(rtc, list(gs._ecef(LON0, LAT0, 0)))

    def test_a_normal_up_points_away_from_the_earth(self):
        out, rtc = er.to_rtc(glb([[0, 0, 0]], [[0, 1, 0]]), LON0, LAT0, GEOID)
        doc, binary, _ = p3.glb_chunks(out)
        nx, ny, nz = np.frombuffer(binary[12:24], np.float32)
        n = np.array([nx, -nz, ny])
        up = np.array(gs._ecef(LON0, LAT0, 1)) - np.array(gs._ecef(LON0, LAT0, 0))
        self.assertGreater(float(n @ up), 0.999)

    def test_the_bounds_of_the_positions_are_written_again(self):
        out, _ = er.to_rtc(glb([[0, 0, 0], [10, 5, -3]], [[0, 1, 0]] * 2), LON0, LAT0, GEOID)
        doc, binary, _ = p3.glb_chunks(out)
        pos = np.frombuffer(binary[:24], np.float32).reshape(2, 3)
        self.assertEqual(doc["accessors"][0]["min"], pos.min(0).tolist())
        self.assertEqual(doc["accessors"][0]["max"], pos.max(0).tolist())


if __name__ == "__main__":
    unittest.main()
