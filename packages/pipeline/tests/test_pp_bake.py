"""pp_bake: the look of untextured PLATEAU buildings written into the GLB itself (roof photo, wall colour)."""
import io
import json
import math
import struct
import unittest

import numpy as np
from PIL import Image

from support import import_pipeline

pp_bake = import_pipeline("buildings.pp_bake")
glb_spatial = import_pipeline("buildings.glb_spatial")
plateau_3d = import_pipeline("buildings.plateau_3d")
city_proxy = import_pipeline("buildings.city_proxy")

LON, LAT, H = 139.69, 35.69, 40.0
RTC = list(glb_spatial._ecef(LON, LAT, H))


def enu_to_gltf(points_enu):
    """Local east/north/up metres around (LON, LAT, H) -> glTF positions of a tile whose RTC is that point."""
    lo, la = math.radians(LON), math.radians(LAT)
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.array([-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)])
    up = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])
    ecef = np.asarray(points_enu, float) @ np.stack([east, north, up])
    return np.stack([ecef[:, 0], ecef[:, 2], -ecef[:, 1]], axis=1).astype(np.float32)


def glb(doc, binary):
    j = json.dumps(doc).encode()
    j += b" " * (-len(j) % 4)
    binary += b"\0" * (-len(binary) % 4)
    return (struct.pack("<4sII", b"glTF", 2, 28 + len(j) + len(binary)) + struct.pack("<I4s", len(j), b"JSON") + j
            + struct.pack("<I4s", len(binary), b"BIN\0") + binary)


def tile():
    """Building 0: a flat roof 10 m square, 20 m up, 30-40 m east; a south-facing wall below it.
    Building 1: the same shapes 30-40 m west, in a primitive whose material has its own photo texture."""
    def shapes(x0):
        roof = [[x0, 0, 20], [x0 + 10, 0, 20], [x0 + 10, 10, 20], [x0, 10, 20]]
        wall = [[x0, 0, 0], [x0 + 10, 0, 0], [x0 + 10, 0, 20], [x0, 0, 20]]
        quads = [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
        return roof + wall, quads
    parts, views, accessors = [], [], []

    def add(arr, ctype, typ, minmax=False):
        raw = np.ascontiguousarray(arr).tobytes()
        off = sum(len(p) for p in parts)
        parts.append(raw + b"\0" * (-len(raw) % 4))
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(raw)})
        acc = {"bufferView": len(views) - 1, "componentType": ctype, "count": len(arr), "type": typ}
        if minmax:
            acc.update(min=np.min(arr, 0).tolist(), max=np.max(arr, 0).tolist())
        accessors.append(acc)
        return len(accessors) - 1

    prims = []
    for batch, x0 in ((0, 30.0), (1, -40.0)):
        pts, faces = shapes(x0)
        p = add(enu_to_gltf(pts), 5126, "VEC3", True)
        b = add(np.full(8, batch, np.float32), 5126, "SCALAR")
        i = add(np.asarray(faces, np.uint32).reshape(-1), 5125, "SCALAR")
        prims.append({"attributes": {"POSITION": p, "_BATCHID": b}, "indices": i, "material": batch})
    png = io.BytesIO()
    Image.new("RGB", (4, 4), (0, 255, 0)).save(png, "PNG")
    off = sum(len(p) for p in parts)
    parts.append(png.getvalue() + b"\0" * (-len(png.getvalue()) % 4))
    views.append({"buffer": 0, "byteOffset": off, "byteLength": len(png.getvalue())})
    binary = b"".join(parts)
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}], "bufferViews": views,
           "accessors": accessors, "meshes": [{"primitives": prims}],
           "materials": [{"name": "plain", "pbrMetallicRoughness": {"baseColorFactor": [0.8, 0.8, 0.8, 1]}},
                         {"name": "photo", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
           "textures": [{"source": 0}], "images": [{"bufferView": len(views) - 1, "mimeType": "image/png"}],
           "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}]}
    return glb(doc, binary)


def roof_photo():
    """West half red, east half blue, over 200 m around the tile."""
    dlon = 100 / (111320 * math.cos(math.radians(LAT)))
    dlat = 100 / 110950
    img = Image.new("RGB", (200, 200), (255, 0, 0))
    img.paste((0, 0, 255), (100, 0, 200, 200))
    return img, [LON - dlon, LAT - dlat, LON + dlon, LAT + dlat]


def read(payload):
    doc, binary, _ = plateau_3d.glb_chunks(payload)
    return doc, binary


def values(doc, binary, idx):
    return np.asarray(glb_spatial._accessor_values(doc, binary, idx), np.float32)


class BakeUntextured(unittest.TestCase):
    def setUp(self):
        photo, bounds = roof_photo()
        self.colours = [city_proxy.wall_hex("a", 20.0), city_proxy.wall_hex("b", 20.0)]
        self.out = pp_bake.bake_untextured(tile(), RTC, ["a", "b"], self.colours, photo, bounds)
        self.doc, self.bin = read(self.out)
        self.prims = self.doc["meshes"][0]["primitives"]

    def material(self, prim):
        return self.doc["materials"][prim["material"]]

    def test_the_untextured_primitive_splits_into_a_roof_and_walls(self):
        names = sorted(self.material(p)["name"] for p in self.prims)
        self.assertEqual(names, ["photo", "pp-roof", "pp-wall"])

    def test_the_roof_shows_the_photo_where_it_lies(self):
        roof = next(p for p in self.prims if self.material(p)["name"] == "pp-roof")
        uv = values(self.doc, self.bin, roof["attributes"]["TEXCOORD_0"])
        tex = self.doc["textures"][self.material(roof)["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
        view = self.doc["bufferViews"][self.doc["images"][tex["source"]]["bufferView"]]
        start = view.get("byteOffset", 0)
        img = Image.open(io.BytesIO(self.bin[start:start + view["byteLength"]])).convert("RGB")
        u, v = uv.mean(axis=0)
        r, g, b = img.getpixel((min(int(u * img.width), img.width - 1), min(int(v * img.height), img.height - 1)))
        self.assertGreater(b, 200)          # 30-40 m east: the blue half
        self.assertLess(r, 60)
        self.assertEqual(len(values(self.doc, self.bin, roof["indices"])), 6)

    def test_the_walls_carry_the_colour_from_id_and_height_as_vertex_colour(self):
        wall = next(p for p in self.prims if self.material(p)["name"] == "pp-wall")
        colour = values(self.doc, self.bin, wall["attributes"]["COLOR_0"])
        hexa = self.colours[0]
        srgb = np.array([int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)])
        linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
        np.testing.assert_allclose(colour[:, :3], np.tile(linear, (len(colour), 1)), atol=1e-4)
        self.assertEqual(len(values(self.doc, self.bin, wall["indices"])), 6)

    def test_both_keep_the_building_ids(self):
        for p in self.prims:
            ids = set(values(self.doc, self.bin, p["attributes"]["_BATCHID"]).reshape(-1).tolist())
            self.assertEqual(ids, {1.0} if self.material(p)["name"] == "photo" else {0.0})

    def test_a_primitive_with_its_own_photo_is_left_alone(self):
        before_doc, before_bin = read(tile())
        photo = next(p for p in self.prims if self.material(p)["name"] == "photo")
        np.testing.assert_array_equal(values(self.doc, self.bin, photo["attributes"]["POSITION"]),
                                      values(before_doc, before_bin, before_doc["meshes"][0]["primitives"][1]["attributes"]["POSITION"]))

    def test_baking_a_baked_tile_changes_nothing(self):
        photo, bounds = roof_photo()
        self.assertEqual(pp_bake.bake_untextured(self.out, RTC, ["a", "b"], self.colours, photo, bounds), self.out)



class DracoTile(unittest.TestCase):
    def test_a_draco_compressed_untextured_tile_is_written_back_plain(self):
        from test_glb_strip import draco_glb
        photo, bounds = roof_photo()
        out = pp_bake.bake_untextured(draco_glb(), RTC, ["a", "b", "c"], [None, None, None], photo, bounds)
        doc, binary = read(out)
        self.assertNotIn("KHR_draco_mesh_compression", json.dumps(doc))
        faces = sum(len(values(doc, binary, p["indices"])) for p in doc["meshes"][0]["primitives"])
        self.assertEqual(faces, 6)


if __name__ == "__main__":
    unittest.main()
