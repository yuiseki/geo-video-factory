"""pp_tiles: PLATEAU++ kept once per tile and shared by every box; a box is a manifest and links into the store."""
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import import_pipeline

pt = import_pipeline("buildings.pp_tiles")
gsf = import_pipeline("buildings.gsi_footprints")

REGION_DEG = [139.79, 35.70, 139.80, 35.71]


def leaf(name, deg=REGION_DEG):
    return {"uri": f"https://tiles.example/{name}.b3dm", "region": [math.radians(v) for v in deg] + [0, 50], "depth": 3}


def square(lon, lat, d=0.00005, fid="gsi/x"):
    ring = [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]
    return {"type": "Feature", "id": fid, "properties": {"vt_code": "3101"},
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


class Store(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": self.root})
        env.start()
        self.addCleanup(env.stop)
        self.fetched = []
        self.osm_boxes = []
        self.photo_boxes = []

        def fetch(uri):
            self.fetched.append(uri)
            return b"raw:" + uri.encode()

        self.fetch = fetch
        patches = [
            mock.patch("buildings.plateau_3d._parse_tile",
                       side_effect=lambda raw, uri: (b"glb:" + uri.encode(), ["a", "b"], [1.0, 2.0, 3.0], {})),
            mock.patch("buildings.plateau_3d._resize_glb_textures", side_effect=lambda glb, limit: glb),
            mock.patch("buildings.glb_spatial.extract_glb_feature_centroids",
                       return_value={"a": [139.795, 35.705], "b": [139.796, 35.705]}),
            mock.patch("buildings.glb_spatial.extract_glb_feature_shapes", return_value={
                "a": {"lonlat": [139.795, 35.705], "height": 20.0, "area": 400.0},
                "b": {"lonlat": [139.796, 35.705], "height": 155.0, "area": 2.0}}),
            mock.patch("buildings.glb_spatial.extract_glb_feature_heights",
                       return_value={"a": {"lonlat": [139.795, 35.705], "height": 20.0}}),
            mock.patch("buildings.plausibility.implausible", side_effect=self.implausible),
            mock.patch("buildings.glb_strip.drop_features", side_effect=lambda glb, drop: glb + b"-dropped"),
            mock.patch("buildings.gsi_footprints.orthophoto_texture", side_effect=self.photo),
            mock.patch("buildings.pp_bake.bake_untextured", side_effect=lambda glb, *a: glb + b"-baked"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def implausible(self, shapes, osm):
        return {"b": "needle"}

    def photo(self, box, gsi, zoom=18):
        self.photo_boxes.append(box)
        return object(), box

    def osm(self, box):
        self.osm_boxes.append(box)
        return []

    def test_a_plateau_tile_is_baked_once_under_the_raw_caches_name(self):
        item = leaf("t1")
        with mock.patch.object(pt, "osm_around", side_effect=self.osm):
            first = pt.plateau_tile(item, Path("/gsi"), self.fetch)
            again = pt.plateau_tile(item, Path("/gsi"), self.fetch)
        d = pt.digest(item["uri"])
        self.assertEqual(first["glb"], f"plateau/{d[:2]}/{d}.glb")
        self.assertEqual((pt.store() / first["glb"]).read_bytes(), b"glb:" + item["uri"].encode() + b"-dropped-baked")
        self.assertEqual(again, first)
        self.assertEqual(len(self.fetched), 1)                    # the second box reads the store

    def test_a_tile_is_judged_by_what_stands_around_the_tile_not_around_a_box(self):
        from buildings.plateau_pp import CONTEXT_M, grow
        with mock.patch.object(pt, "osm_around", side_effect=self.osm):
            entry = pt.plateau_tile(leaf("t2"), Path("/gsi"), self.fetch)
        self.assertEqual(self.osm_boxes, [grow(pt._degrees(leaf("t2")["region"]), CONTEXT_M)])
        self.assertEqual([round(v, 9) for v in self.photo_boxes[0]], [round(v, 9) for v in REGION_DEG])
        self.assertEqual([r["id"] for r in entry["removed_buildings"]], ["b"])
        self.assertEqual(list(entry["heights"]), ["a"])               # what the filled-in tiles calibrate and shade on


class Proxy(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": self.root})
        env.start()
        self.addCleanup(env.stop)
        self.x, self.y = gsf.tiles_for_bbox([139.7951, 35.7051, 139.7951, 35.7051], 16)[0]
        w, s, e, n = gsf.tile_bbox(16, self.x, self.y)
        self.mine = square(w + 0.0002, s + 0.0002, fid="gsi/mine")
        self.next = square(e + 0.0002, s + 0.0002, fid="gsi/next")        # its centre lies in the next tile east
        self.proxy_calls = []

        def proxy(features, bbox, out_dir, **kw):
            self.proxy_calls.append((features, bbox, kw))
            (Path(out_dir) / "models").mkdir(parents=True, exist_ok=True)
            for kind in ("city-proxy", "city-shadow"):
                (Path(out_dir) / "models" / f"{kind}.glb").write_bytes(kind.encode())
            (Path(out_dir) / "models" / "b.json").write_text("{}")
            return {"center": [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2], "tiles": [
                {"glb": "models/city-proxy.glb", "kind": "city-proxy", "frame": "enu", "ids": ["gsi/mine"],
                 "buildings": "models/b.json", "roof_texture": {"bounds_m": [-1, -1, 1, 1]}},
                {"glb": "models/city-shadow.glb", "kind": "city-shadow", "frame": "enu", "ids": []}]}

        self.rtc_calls = []

        def to_rtc(raw, lon0, lat0, geoid):
            self.rtc_calls.append((lon0, lat0))
            return raw + b"-ecef", [9.0, 9.0, 9.0]

        patches = [
            mock.patch("buildings.gsi_footprints.fetch_gsi_buildings", return_value=[self.mine, self.next]),
            mock.patch("buildings.gsi_footprints.dem_sampler", return_value=lambda lon, lat: 0.0),
            mock.patch("buildings.gsi_footprints.orthophoto_texture", side_effect=lambda box, gsi, zoom=18: (object(), box)),
            mock.patch("buildings.plateau_3d._leaf_items", return_value=[]),
            mock.patch("buildings.city_proxy.build_city_proxy_tile", side_effect=proxy),
            mock.patch("buildings.pp_bake.bake_proxy", side_effect=lambda raw, ids, photo, bounds: raw + b"-baked"),
            mock.patch("buildings.enu_rtc.to_rtc", side_effect=to_rtc),
            mock.patch("buildings.plateau_pp.cell_models", return_value=lambda lon, lat: {}),
            mock.patch.object(pt, "osm_around", return_value=[]),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_only_the_footprints_whose_centre_lies_in_the_tile_are_filled_in_there(self):
        entries = pt.proxy_tile(self.x, self.y, "tileset", Path("/gsi"), "plateau-pp", lambda u: b"")
        features, bbox, kw = self.proxy_calls[0]
        self.assertEqual([f["id"] for f in features], ["gsi/mine"])
        self.assertEqual(bbox, gsf.tile_bbox(16, self.x, self.y))
        self.assertEqual([e["kind"] for e in entries], ["city-proxy", "city-shadow"])

    def test_filled_in_tiles_are_written_once_in_ecef_around_the_tiles_own_centre(self):
        entries = pt.proxy_tile(self.x, self.y, "tileset", Path("/gsi"), "plateau-pp", lambda u: b"")
        again = pt.proxy_tile(self.x, self.y, "tileset", Path("/gsi"), "plateau-pp", lambda u: b"")
        self.assertEqual(again, entries)
        self.assertEqual(len(self.proxy_calls), 1)
        w, s, e, n = gsf.tile_bbox(16, self.x, self.y)
        self.assertEqual(self.rtc_calls[0], ((w + e) / 2, (s + n) / 2))
        self.assertTrue(all("frame" not in e and e["rtc"] == [9.0, 9.0, 9.0] for e in entries))
        self.assertEqual((pt.store() / entries[0]["glb"]).read_bytes(), b"city-proxy-baked-ecef")
        self.assertTrue((pt.store() / entries[0]["buildings"]).exists())


class Assemble(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        env = mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": self.root})
        env.start()
        self.addCleanup(env.stop)

        def plateau_tile(item, gsi, fetch):
            rel = f"plateau/{pt.digest(item['uri'])[:2]}/{pt.digest(item['uri'])}.glb"
            path = pt.store() / rel
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(item["uri"].encode())
            return {"source": item["uri"], "glb": rel, "rtc": [0, 0, 0], "ids": ["a"], "heights": {"a": [0, 0, 1]}}

        patches = [
            mock.patch.object(pt, "plateau_tile", side_effect=plateau_tile),
            mock.patch.object(pt, "proxy_tile", return_value=[]),
            mock.patch("buildings.plateau_3d._cached_fetcher", return_value=lambda u: b""),
            mock.patch("buildings.plateau_3d._leaf_items",
                       side_effect=lambda tileset, box, fetch: [leaf("west"), leaf("east")] if box[0] > 139.5
                       else [leaf("west")]),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def files(self):
        return sorted(p for p in Path(self.root).rglob("*.glb") if not p.is_symlink() and "boxes" not in p.parts)

    def test_a_box_is_a_manifest_and_relative_links_into_the_store(self):
        out = Path(self.root) / "project" / "assets" / "buildings"
        m = pt.assemble(out, [139.79, 35.70, 139.80, 35.71], "tileset", Path("/gsi"))
        for tile in m["tiles"]:
            link = out / tile["glb"]
            self.assertTrue(link.is_symlink())
            self.assertFalse(os.path.isabs(os.readlink(link)))
            self.assertEqual(link.resolve().parent.parent.name, "plateau")
            self.assertNotIn("heights", tile)
        self.assertEqual(json.loads((out / "manifest.json").read_text())["tile_count"], 2)

    def test_a_second_box_over_the_same_tiles_adds_no_tile_files(self):
        pt.assemble(Path(self.root) / "a", [139.79, 35.70, 139.80, 35.71], "tileset", Path("/gsi"))
        before = self.files()
        pt.assemble(Path(self.root) / "b", [139.795, 35.70, 139.805, 35.71], "tileset", Path("/gsi"))
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
