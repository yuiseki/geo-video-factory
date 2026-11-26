"""pp_bake: the look of PLATEAU++ written into the GLBs themselves (roof photo, wall colour, windows, tone)."""
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
facade_tiles = import_pipeline("buildings.facade_tiles")

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


def tile(photo_rgb=(128, 128, 128)):
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
    Image.new("RGB", (4, 4), photo_rgb).save(png, "PNG")
    off = sum(len(p) for p in parts)
    parts.append(png.getvalue() + b"\0" * (-len(png.getvalue()) % 4))
    views.append({"buffer": 0, "byteOffset": off, "byteLength": len(png.getvalue())})
    binary = b"".join(parts)
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}], "bufferViews": views,
           "accessors": accessors, "meshes": [{"primitives": prims}],
           "materials": [{"name": "plain", "pbrMetallicRoughness": {"baseColorFactor": [0.8, 0.8, 0.8, 1]}},
                         {"name": "photo", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "baseColorFactor": [0.7, 0.7, 0.7, 1], "metallicFactor": 0.5, "roughnessFactor": 0.3}}],
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


def image_of(doc, binary, texture_index):
    view = doc["bufferViews"][doc["images"][doc["textures"][texture_index]["source"]]["bufferView"]]
    start = view.get("byteOffset", 0)
    return Image.open(io.BytesIO(binary[start:start + view["byteLength"]])).convert("RGB")


def palette_colour(hexa, gain):
    """The renderer reads the palette bytes as they are (no sRGB decode) and applies the gain."""
    return np.array([int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]) * gain


class BakeUntextured(unittest.TestCase):
    def setUp(self):
        photo, bounds = roof_photo()
        self.colours = [city_proxy.wall_hex("a", 20.0), city_proxy.wall_hex("b", 20.0)]
        self.out = pp_bake.bake_untextured(tile(), RTC, ["a", "b"], self.colours, photo, bounds)
        self.doc, self.bin = read(self.out)
        self.prims = self.doc["meshes"][0]["primitives"]

    def material(self, prim):
        return self.doc["materials"][prim["material"]]

    def named(self, name):
        return next(p for p in self.prims if self.material(p)["name"] == name)

    def test_the_untextured_primitive_splits_into_a_roof_and_walls_of_its_facade_style(self):
        names = sorted(self.material(p)["name"] for p in self.prims)
        self.assertEqual(names, ["photo", "pp-roof", "pp-wall-curtain"])      # 20 m: a tall building

    def test_the_roof_shows_the_photo_where_it_lies(self):
        roof = self.named("pp-roof")
        uv = values(self.doc, self.bin, roof["attributes"]["TEXCOORD_0"])
        img = image_of(self.doc, self.bin, self.material(roof)["pbrMetallicRoughness"]["baseColorTexture"]["index"])
        u, v = uv.mean(axis=0)
        r, g, b = img.getpixel((min(int(u * img.width), img.width - 1), min(int(v * img.height), img.height - 1)))
        self.assertGreater(b, 200)          # 30-40 m east: the blue half
        self.assertLess(r, 60)
        self.assertEqual(len(values(self.doc, self.bin, roof["indices"])), 6)

    def test_the_walls_carry_the_palette_colour_with_the_renderers_gain(self):
        wall = self.named("pp-wall-curtain")
        colour = values(self.doc, self.bin, wall["attributes"]["COLOR_0"])
        expected = palette_colour(self.colours[0], pp_bake.PALETTE_WALL_GAIN)
        np.testing.assert_allclose(colour[:, :3], np.tile(expected, (len(colour), 1)), atol=1e-4)
        self.assertEqual(len(values(self.doc, self.bin, wall["indices"])), 6)

    def test_the_walls_repeat_the_window_pattern_in_metres(self):
        wall = self.named("pp-wall-curtain")
        mat = self.material(wall)
        sampler = self.doc["samplers"][self.doc["textures"][mat["pbrMetallicRoughness"]["baseColorTexture"]["index"]]["sampler"]]
        self.assertEqual((sampler["wrapS"], sampler["wrapT"]), (10497, 10497))
        self.assertIn("emissiveTexture", mat)
        self.assertEqual(mat["emissiveFactor"], [0.0, 0.0, 0.0])              # lights off: the renderer raises it at night
        uv = values(self.doc, self.bin, wall["attributes"]["TEXCOORD_0"])
        bay, storey = facade_tiles.module("curtain", "a")
        self.assertAlmostEqual(float(np.ptp(uv[:, 0])), 10 / (bay * facade_tiles.BAYS), places=3)
        self.assertAlmostEqual(float(np.ptp(uv[:, 1])), 20 / (storey * facade_tiles.STOREYS), places=3)
        self.assertAlmostEqual(float(uv[:, 1].max()), 0.0, places=3)           # the ground at the top edge, going up = down the image

    def test_both_keep_the_building_ids(self):
        for p in self.prims:
            ids = set(values(self.doc, self.bin, p["attributes"]["_BATCHID"]).reshape(-1).tolist())
            self.assertEqual(ids, {1.0} if self.material(p)["name"] == "photo" else {0.0})

    def test_a_photo_textured_primitive_keeps_its_geometry(self):
        before_doc, before_bin = read(tile())
        photo = self.named("photo")
        np.testing.assert_array_equal(values(self.doc, self.bin, photo["attributes"]["POSITION"]),
                                      values(before_doc, before_bin, before_doc["meshes"][0]["primitives"][1]["attributes"]["POSITION"]))

    def test_a_photo_material_becomes_rough_non_metal_double_sided_without_the_extra_tint(self):
        mat = self.material(self.named("photo"))
        pbr = mat["pbrMetallicRoughness"]
        self.assertEqual(pbr["metallicFactor"], 0.0)
        self.assertGreaterEqual(pbr["roughnessFactor"], 0.85)
        self.assertTrue(mat["doubleSided"])
        self.assertEqual(pbr["baseColorFactor"], [1.0, 1.0, 1.0, 1.0])        # mid grey photo: no tone-down

    def test_a_photo_is_brought_to_the_aerial_photo_tone(self):
        img = image_of(self.doc, self.bin, self.material(self.named("photo"))["pbrMetallicRoughness"]["baseColorTexture"]["index"])
        lin = ((128 / 255 + 0.055) / 1.055) ** 2.4
        out = lin ** pp_bake.PLATEAU_PHOTO_GAMMA
        srgb = 1.055 * out ** (1 / 2.4) - 0.055
        self.assertAlmostEqual(img.getpixel((1, 1))[0], round(srgb * 255), delta=2)

    def test_a_washed_out_photo_is_toned_down(self):
        photo, bounds = roof_photo()
        doc, _ = read(pp_bake.bake_untextured(tile((250, 250, 250)), RTC, ["a", "b"], self.colours, photo, bounds))
        mat = next(m for m in doc["materials"] if m["name"] == "photo")
        self.assertEqual(mat["pbrMetallicRoughness"]["baseColorFactor"], [0.64, 0.64, 0.64, 1.0])

    def test_baking_a_baked_tile_changes_nothing(self):
        photo, bounds = roof_photo()
        self.assertEqual(pp_bake.bake_untextured(self.out, RTC, ["a", "b"], self.colours, photo, bounds), self.out)
        self.assertEqual(self.doc["asset"]["extras"]["plateau_pp_bake"], pp_bake.BAKE_VERSION)

    def test_a_photo_referenced_through_ext_texture_webp_is_toned_too(self):
        doc, binary = read(tile((250, 250, 250)))
        doc["textures"] = [{"extensions": {"EXT_texture_webp": {"source": 0}}}]
        doc["extensionsUsed"] = ["EXT_texture_webp"]
        photo, bounds = roof_photo()
        out, _ = read(pp_bake.bake_untextured(glb(doc, binary), RTC, ["a", "b"], self.colours, photo, bounds))
        mat = next(m for m in out["materials"] if m["name"] == "photo")
        self.assertEqual(mat["pbrMetallicRoughness"]["baseColorFactor"], [0.64, 0.64, 0.64, 1.0])

    def test_a_low_building_gets_the_house_pattern(self):
        photo, bounds = roof_photo()
        colours = [city_proxy.wall_hex("a", 6.0), city_proxy.wall_hex("b", 6.0)]
        doc, _ = read(pp_bake.bake_untextured(tile(), RTC, ["a", "b"], colours, photo, bounds))
        self.assertIn("pp-wall-house", [m["name"] for m in doc["materials"]])


def proxy_tile():
    """A filled-in house in the city_proxy layout: Y-up local metres, unindexed, uv = (along the wall, above ground)."""
    roof = [[30, 6, 0], [40, 6, 0], [40, 6, -10], [30, 6, 0], [40, 6, -10], [30, 6, -10]]
    wall = [[30, 0, 0], [40, 0, 0], [40, 6, 0], [30, 0, 0], [40, 6, 0], [30, 6, 0]]
    pos = np.asarray(roof + wall, np.float32)
    normal = np.asarray([[0, 1, 0]] * 6 + [[0, 0, 1]] * 6, np.float32)
    colour = np.asarray([[0.3, 0.2, 0.1]] * 6 + [[0.8, 0.7, 0.6]] * 6, np.float32)
    uv = np.asarray([[0, 6]] * 6 + [[0, 0], [10, 0], [10, 6], [0, 0], [10, 6], [0, 6]], np.float32)
    batch = np.zeros((12, 1), np.float32)
    style = np.asarray([[0, 6]] * 12, np.float32)
    parts, views, accessors, attrs = [], [], [], {}
    for name, arr in (("POSITION", pos), ("NORMAL", normal), ("COLOR_0", colour), ("TEXCOORD_0", uv), ("_BATCHID", batch), ("_STYLE", style)):
        raw = arr.tobytes()
        views.append({"buffer": 0, "byteOffset": sum(len(p) for p in parts), "byteLength": len(raw)})
        parts.append(raw)
        acc = {"bufferView": len(views) - 1, "componentType": 5126, "count": 12, "type": {1: "SCALAR", 2: "VEC2", 3: "VEC3"}[arr.shape[1]]}
        if name == "POSITION":
            acc.update(min=pos.min(0).tolist(), max=pos.max(0).tolist())
        accessors.append(acc)
        attrs[name] = len(accessors) - 1
    binary = b"".join(parts)
    doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}], "bufferViews": views, "accessors": accessors,
           "materials": [{"name": "city-proxy", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.9}}],
           "meshes": [{"primitives": [{"attributes": attrs, "material": 0}]}], "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}]}
    return glb(doc, binary)


class BakeProxy(unittest.TestCase):
    def setUp(self):
        img = Image.new("RGB", (200, 200), (255, 0, 0))
        img.paste((0, 0, 255), (100, 0, 200, 200))
        self.out = pp_bake.bake_proxy(proxy_tile(), ["gsi/1"], img, [-100.0, -100.0, 100.0, 100.0])
        self.doc, self.bin = read(self.out)
        self.prims = self.doc["meshes"][0]["primitives"]

    def named(self, name):
        return next(p for p in self.prims if self.doc["materials"][p["material"]]["name"] == name)

    def test_roofs_show_the_photo_and_walls_the_pattern_of_their_style(self):
        names = sorted(self.doc["materials"][p["material"]]["name"] for p in self.prims)
        self.assertEqual(names, ["pp-roof", "pp-wall-house"])
        roof = self.named("pp-roof")
        uv = values(self.doc, self.bin, roof["attributes"]["TEXCOORD_0"])
        img = image_of(self.doc, self.bin, self.doc["materials"][roof["material"]]["pbrMetallicRoughness"]["baseColorTexture"]["index"])
        u, v = uv.mean(axis=0)
        self.assertGreater(img.getpixel((min(int(u * img.width), img.width - 1), min(int(v * img.height), img.height - 1)))[2], 200)

    def test_walls_keep_their_colour_with_the_proxy_gain_and_map_metres_to_the_pattern(self):
        wall = self.named("pp-wall-house")
        colour = values(self.doc, self.bin, wall["attributes"]["COLOR_0"])
        np.testing.assert_allclose(colour[:, :3], np.tile(np.array([0.8, 0.7, 0.6]) * pp_bake.PROXY_WALL_GAIN, (6, 1)), atol=1e-5)
        uv = values(self.doc, self.bin, wall["attributes"]["TEXCOORD_0"])
        bay, storey = facade_tiles.module("house", "gsi/1")
        self.assertAlmostEqual(float(np.ptp(uv[:, 0])), 10 / (bay * facade_tiles.BAYS), places=4)
        self.assertAlmostEqual(float(np.ptp(uv[:, 1])), 6 / (storey * facade_tiles.STOREYS), places=4)

    def test_baking_twice_changes_nothing(self):
        img = Image.new("RGB", (8, 8))
        self.assertEqual(pp_bake.bake_proxy(self.out, ["gsi/1"], img, [-100.0, -100.0, 100.0, 100.0]), self.out)


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
