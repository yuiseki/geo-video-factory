import json
import struct
import unittest

import DracoPy
import numpy as np

from buildings import glb_spatial as gs
from buildings.glb_strip import drop_features

# two buildings, one triangle each: feature 0 near the origin, feature 1 five metres east
POINTS = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1], [5, 0, 0], [6, 0, 0], [5, 0, 1]], np.float32)
FACES = np.array([[0, 1, 2], [3, 4, 5]], np.uint32)
BATCH = np.array([0, 0, 0, 1, 1, 1], np.float32)
IMAGE = b"\x89PNG fake image bytes"


def _glb(document, binary):
    j = json.dumps(document).encode()
    j += b" " * (-len(j) % 4)
    binary += b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(j) + 8 + len(binary)
    return (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<I4s", len(j), b"JSON") + j
            + struct.pack("<I4s", len(binary), b"BIN\0") + binary)


def plain_glb():
    parts = [POINTS.tobytes(), BATCH.tobytes(), FACES.reshape(-1).tobytes(), IMAGE]
    views, off = [], 0
    for p in parts:
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(p)})
        off += len(p) + (-len(p) % 4)
    binary = b"".join(p + b"\0" * (-len(p) % 4) for p in parts)
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}], "bufferViews": views,
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 6, "type": "VEC3",
                          "min": [0, 0, 0], "max": [6, 0, 1]},
                         {"bufferView": 1, "componentType": 5126, "count": 6, "type": "SCALAR"},
                         {"bufferView": 2, "componentType": 5125, "count": 6, "type": "SCALAR"}],
           "images": [{"bufferView": 3, "mimeType": "image/png"}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "_BATCHID": 1}, "indices": 2}]}],
           "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}]}
    return _glb(doc, binary)


def draco_glb():
    enc = DracoPy.encode(POINTS, FACES, normals=np.tile([0.0, -1.0, 0.0], (6, 1)), tex_coord=np.zeros((6, 2)),
                         generic_attributes={7: BATCH.astype(np.float64).reshape(-1, 1)}, preserve_order=True)
    ids = {a["attribute_type"]: a["unique_id"] for a in DracoPy.decode(enc).attributes}
    binary = enc + b"\0" * (-len(enc) % 4)
    doc = {"asset": {"version": "2.0"}, "extensionsUsed": ["KHR_draco_mesh_compression"],
           "extensionsRequired": ["KHR_draco_mesh_compression"],
           "buffers": [{"byteLength": len(binary)}], "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(enc)}],
           "accessors": [{"componentType": 5126, "count": 6, "type": "VEC3", "min": [0, 0, 0], "max": [6, 0, 1]},
                         {"componentType": 5126, "count": 6, "type": "VEC3"},
                         {"componentType": 5126, "count": 6, "type": "VEC2"},
                         {"componentType": 5126, "count": 6, "type": "SCALAR"},
                         {"componentType": 5125, "count": 6, "type": "SCALAR"}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2, "_BATCHID": 3},
                                       "indices": 4, "material": 0, "extensions": {"KHR_draco_mesh_compression": {
                                           "bufferView": 0, "attributes": {"POSITION": ids[0], "NORMAL": ids[1],
                                                                          "TEXCOORD_0": ids[3], "_BATCHID": ids[4]}}}}]}],
           "materials": [{"name": "photo"}], "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}]}
    return _glb(doc, binary)


def kept_features(payload):
    """Feature ids that still have a triangle."""
    doc, binary, _ = gs.glb_chunks(payload)
    prim = doc["meshes"][0]["primitives"][0]
    if "KHR_draco_mesh_compression" in prim.get("extensions", {}):
        return {0, 1}
    idx = [int(v[0]) for v in gs._accessor_values(doc, binary, prim["indices"])]
    feat = [int(v[0]) for v in gs._accessor_values(doc, binary, prim["attributes"]["_BATCHID"])]
    return {feat[i] for i in idx}


class DropFeatures(unittest.TestCase):
    def test_plain_primitive_loses_only_the_dropped_building(self):
        out = drop_features(plain_glb(), {1})
        self.assertEqual(kept_features(out), {0})

    def test_other_buffer_views_survive_byte_for_byte(self):
        out = drop_features(plain_glb(), {1})
        doc, binary, _ = gs.glb_chunks(out)
        view = doc["bufferViews"][doc["images"][0]["bufferView"]]
        start = view.get("byteOffset", 0)
        self.assertEqual(binary[start:start + view["byteLength"]], IMAGE)

    def test_draco_primitive_is_decoded_and_keeps_its_attributes_and_material(self):
        out = drop_features(draco_glb(), {1})
        doc, binary, _ = gs.glb_chunks(out)
        prim = doc["meshes"][0]["primitives"][0]
        self.assertNotIn("extensions", prim)
        self.assertEqual(set(prim["attributes"]), {"POSITION", "NORMAL", "TEXCOORD_0", "_BATCHID"})
        self.assertEqual(prim["material"], 0)
        self.assertNotIn("KHR_draco_mesh_compression", doc.get("extensionsRequired", []))
        self.assertEqual(kept_features(out), {0})

    def test_nothing_to_drop_returns_the_payload_unchanged(self):
        payload = draco_glb()
        self.assertEqual(drop_features(payload, {9}), payload)

    def test_feature_heights_no_longer_see_the_dropped_building(self):
        out = drop_features(plain_glb(), {1})
        rtc = [0.0, 0.0, 6378137.0]
        self.assertEqual(set(gs.extract_glb_feature_heights(out, rtc, ["a", "b"])), {"a"})



class FeatureShapes(unittest.TestCase):
    def test_footprint_area_and_height_per_feature(self):
        # a flat 10 m x 10 m square on the ground, given as ECEF offsets from the tile centre (glTF y = ECEF z,
        # glTF z = -ECEF y, as PLATEAU tiles come): area 100 m2, height 0
        lon, lat, dlat, dlon = 139.7, 35.66, 10 / 111320.0, 10 / (111320.0 * np.cos(np.radians(35.66)))
        rtc = list(gs._ecef(lon, lat, 0.0))
        corners = [gs._ecef(lon + x, lat + y, 0.0) for x, y in ((0, 0), (dlon, 0), (dlon, dlat), (0, dlat))]
        pts = np.array([[c[0] - rtc[0], c[2] - rtc[2], -(c[1] - rtc[1])] for c in corners], np.float32)
        faces = np.array([0, 1, 2, 0, 2, 3], np.uint32)
        batch = np.zeros(4, np.float32)
        parts = [pts.tobytes(), batch.tobytes(), faces.tobytes()]
        views, off = [], 0
        for p in parts:
            views.append({"buffer": 0, "byteOffset": off, "byteLength": len(p)})
            off += len(p)
        doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": off}], "bufferViews": views,
               "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"},
                             {"bufferView": 1, "componentType": 5126, "count": 4, "type": "SCALAR"},
                             {"bufferView": 2, "componentType": 5125, "count": 6, "type": "SCALAR"}],
               "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "_BATCHID": 1}, "indices": 2}]}],
               "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}]}
        s = gs.extract_glb_feature_shapes(_glb(doc, b"".join(parts)), rtc, ["a"])["a"]
        self.assertAlmostEqual(s["area"], 100.0, delta=2.0)
        self.assertLess(s["height"], 0.5)


if __name__ == "__main__":
    unittest.main()
