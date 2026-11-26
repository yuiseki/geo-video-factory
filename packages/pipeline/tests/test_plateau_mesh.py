import io
import json
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from buildings import glb_spatial  # noqa: E402
from buildings import plateau_mesh as pm  # noqa: E402

# At lon 0, lat 0 the frame is easy to read: ECEF x is up, y is east, z is north. A tile's local glTF position
# (x, y, z) sits at rtc + (x, -z, y), so east = -z, north = y, up = x.
RTC = list(glb_spatial._ecef(0.0, 0.0, 0.0))


def glb(positions, indices=None, translation=None, draco=False):
    positions = np.asarray(positions, np.float32)
    prim, views, accessors, binary = {}, [], [], b""
    if draco:
        import DracoPy
        faces = np.arange(len(positions)) if indices is None else np.asarray(indices)
        binary = DracoPy.encode(positions, faces.reshape(-1, 3), quantization_bits=30)
        views.append({"buffer": 0, "byteOffset": 0, "byteLength": len(binary)})
        prim = {"attributes": {"POSITION": 0}, "extensions": {"KHR_draco_mesh_compression": {
            "bufferView": 0, "attributes": {"POSITION": 0}}}}
        accessors.append({"componentType": 5126, "count": len(positions), "type": "VEC3"})
    else:
        binary = positions.tobytes()
        views.append({"buffer": 0, "byteOffset": 0, "byteLength": len(binary)})
        accessors.append({"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3"})
        prim = {"attributes": {"POSITION": 0}}
        if indices is not None:
            raw = np.asarray(indices, np.uint16).tobytes()
            views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(raw)})
            accessors.append({"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"})
            prim["indices"] = 1
            binary += raw
    binary += b"\0" * (-len(binary) % 4)
    node = {"mesh": 0}
    if translation:
        node["translation"] = translation
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [node],
           "meshes": [{"primitives": [prim]}], "buffers": [{"byteLength": len(binary)}], "bufferViews": views,
           "accessors": accessors}
    raw = json.dumps(doc).encode()
    raw += b" " * (-len(raw) % 4)
    return (struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(raw) + 8 + len(binary))
            + struct.pack("<I4s", len(raw), b"JSON") + raw + struct.pack("<I4s", len(binary), b"BIN\0") + binary)


TRI = [(5, 7, -3), (5, 7, -4), (6, 7, -3)]


class EnuFrameTests(unittest.TestCase):
    def test_a_point_above_the_origin_is_straight_up(self):
        origin, m = pm.enu_frame(139.7, 35.66)
        above = np.array(glb_spatial._ecef(139.7, 35.66, 100.0))
        np.testing.assert_allclose((above - origin) @ m.T, [0, 0, 100], atol=1e-6)

    def test_axes_are_east_north_up(self):
        origin, m = pm.enu_frame(139.7, 35.66)
        np.testing.assert_allclose(m @ m.T, np.eye(3), atol=1e-12)
        north = (np.array(glb_spatial._ecef(139.7, 35.661, 0.0)) - origin) @ m.T
        east = (np.array(glb_spatial._ecef(139.701, 35.66, 0.0)) - origin) @ m.T
        self.assertGreater(north[1], 100)
        self.assertLess(abs(north[0]), 0.01)
        self.assertGreater(east[0], 80)
        self.assertLess(abs(east[1]), 0.01)


class GlbTrianglesTests(unittest.TestCase):
    def enu(self, payload):
        origin, m = pm.enu_frame(0.0, 0.0)
        return (pm.glb_triangles(payload, RTC) - origin) @ m.T

    def test_the_y_up_tile_frame_is_turned_into_ecef(self):
        np.testing.assert_allclose(self.enu(glb(TRI)), [[(3, 7, 5), (4, 7, 5), (3, 7, 6)]], atol=1e-3)

    def test_indices_pick_the_corners(self):
        quad = TRI + [(6, 7, -4)]
        out = self.enu(glb(quad, indices=[0, 1, 2, 2, 1, 3]))
        self.assertEqual(out.shape, (2, 3, 3))
        np.testing.assert_allclose(out[1], [(3, 7, 6), (4, 7, 5), (4, 7, 6)], atol=1e-3)

    def test_the_node_transform_is_applied(self):
        out = self.enu(glb(TRI, translation=[10, 0, 0]))
        np.testing.assert_allclose(out[0, 0], (3, 7, 15), atol=1e-3)

    def test_draco_compressed_primitives_are_decoded(self):
        out = self.enu(glb(TRI, draco=True))
        self.assertEqual(out.shape, (1, 3, 3))
        got = sorted(tuple(np.round(p, 2)) for p in out[0])
        self.assertEqual(got, sorted([(3.0, 7.0, 5.0), (4.0, 7.0, 5.0), (3.0, 7.0, 6.0)]))

    def test_a_glb_without_meshes_has_no_triangles(self):
        raw = json.dumps({"asset": {"version": "2.0"}}).encode()
        raw += b" " * (-len(raw) % 4)
        empty = struct.pack("<4sII", b"glTF", 2, 20 + len(raw)) + struct.pack("<I4s", len(raw), b"JSON") + raw
        self.assertEqual(pm.glb_triangles(empty, RTC).shape, (0, 3, 3))


class ManifestTests(unittest.TestCase):
    def folder(self, tmp, tiles):
        for name, payload in tiles.items():
            (tmp / name).write_bytes(payload)
        (tmp / "manifest.json").write_text(json.dumps({"tiles": [{"glb": n, "rtc": RTC} for n in tiles]}))

    def test_every_tile_of_the_manifest_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.folder(tmp, {"a.glb": glb(TRI), "b.glb": glb(TRI, translation=[10, 0, 0])})
            tris = pm.manifest_triangles(tmp, 0.0, 0.0)
        self.assertEqual(tris.dtype, np.float32)
        self.assertEqual(tris.shape, (2, 3, 3))
        np.testing.assert_allclose(tris[:, 0, 2], [5, 15], atol=1e-3)

    def test_filled_in_tiles_stand_upright_around_the_manifest_centre_and_shadows_are_left_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "p.glb").write_bytes(glb([[10, 20, -30], [11, 20, -30], [10, 21, -30]]))   # Y-up local metres
            (tmp / "s.glb").write_bytes(glb(TRI))
            (tmp / "manifest.json").write_text(json.dumps({"center": [139.0, 35.0], "tiles": [
                {"glb": "p.glb", "rtc": RTC, "frame": "enu", "kind": "city-proxy"},
                {"glb": "s.glb", "rtc": RTC, "frame": "enu", "kind": "city-shadow"}]}))
            tris = pm.manifest_triangles(tmp, 139.0, 35.0)
        self.assertEqual(tris.shape, (1, 3, 3))
        np.testing.assert_allclose(tris[0, 0], [10, 30, 20 + pm.GEOID_M], atol=0.05)   # east, north, up from the ellipsoid

    def test_a_manifest_without_triangles_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.folder(tmp, {})
            with self.assertRaisesRegex(ValueError, "no triangles"):
                pm.manifest_triangles(tmp, 0.0, 0.0)

    def test_main_saves_triangles_and_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.folder(tmp, {"a.glb": glb(TRI)})
            buf = io.StringIO()
            with redirect_stdout(buf):
                pm.main([str(tmp), str(tmp / "tris.npz"), "0", "0"])
            saved = np.load(tmp / "tris.npz")
            self.assertEqual(saved["tris"].shape, (1, 3, 3))
            np.testing.assert_allclose(saved["origin"], [0, 0])
        self.assertIn("triangles 1", buf.getvalue())

    def test_main_needs_the_origin(self):
        with self.assertRaises(SystemExit):
            pm.main(["dir", "out.npz"])


if __name__ == "__main__":
    unittest.main()
