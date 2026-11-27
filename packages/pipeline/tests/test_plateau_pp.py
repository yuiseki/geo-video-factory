import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from buildings import glb_spatial as gs
from buildings import plateau_pp

from test_glb_strip import plain_glb


class RemoveImplausible(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "models").mkdir()
        (self.dir / "models" / "t.glb").write_bytes(plain_glb())
        self.manifest = {"tiles": [{"glb": "models/t.glb", "rtc": [0.0, 0.0, 6378137.0], "ids": ["a", "b"]}]}

    def shapes(self, payload, rtc, ids):
        return {"a": {"lonlat": [135.5, 34.66], "height": 20.0, "area": 400.0},
                "b": {"lonlat": [135.5016, 34.6618], "height": 155.0, "area": 2.0}}

    def test_the_needle_leaves_the_tile_and_is_recorded(self):
        with mock.patch.object(gs, "extract_glb_feature_shapes", self.shapes):
            m = plateau_pp.remove_implausible(self.dir, self.manifest, osm_features=[])
        left = gs.extract_glb_feature_heights((self.dir / "models" / "t.glb").read_bytes(), [0.0, 0.0, 6378137.0],
                                              ["a", "b"])
        self.assertEqual(set(left), {"a"})
        self.assertEqual([(r["id"], r["trap"]) for r in m["removed_buildings"]], [("b", "needle")])
        self.assertEqual(m["tiles"][0]["bytes"], (self.dir / "models" / "t.glb").stat().st_size)

    def test_running_it_twice_changes_nothing_more(self):
        with mock.patch.object(gs, "extract_glb_feature_shapes", self.shapes):
            m = plateau_pp.remove_implausible(self.dir, self.manifest, osm_features=[])
            before = (self.dir / "models" / "t.glb").read_bytes()
            m = plateau_pp.remove_implausible(self.dir, m, osm_features=[])
        self.assertEqual((self.dir / "models" / "t.glb").read_bytes(), before)
        self.assertEqual(len(m["removed_buildings"]), 1)


class Overpass(unittest.TestCase):
    def test_no_public_server_is_ever_called(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                plateau_pp.overpass_endpoint()

    def test_the_own_server_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {"OVERPASS_URL": "https://example.invalid/api/interpreter"}):
            self.assertEqual(plateau_pp.overpass_endpoint(), "https://example.invalid/api/interpreter")


class OsmBuildings(unittest.TestCase):
    def test_ways_become_closed_polygons_with_their_tags_and_are_cached(self):
        reply = {"elements": [
            {"type": "node", "id": 1, "lon": 139.0, "lat": 35.0}, {"type": "node", "id": 2, "lon": 139.001, "lat": 35.0},
            {"type": "node", "id": 3, "lon": 139.001, "lat": 35.001},
            {"type": "way", "id": 10, "nodes": [1, 2, 3, 1], "tags": {"building": "yes", "building:levels": "3"}},
            {"type": "way", "id": 11, "nodes": [1, 2, 3], "tags": {"building": "no"}},
            {"type": "way", "id": 12, "nodes": [1, 2], "tags": {"building": "yes"}}]}

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(reply).encode()

        out = Path(tempfile.mkdtemp()) / "osm.geojson"
        with mock.patch.dict(os.environ, {"OVERPASS_URL": "https://example.invalid/api"}), \
                mock.patch("urllib.request.urlopen", return_value=Reply()) as urlopen:
            features = plateau_pp.fetch_osm_buildings([139.0, 35.0, 139.01, 35.01], out)
            again = plateau_pp.fetch_osm_buildings([139.0, 35.0, 139.01, 35.01], out)
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual([f["id"] for f in features], ["way/10"])
        ring = features[0]["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(features[0]["properties"]["building:levels"], "3")
        self.assertEqual(again, features)


class RoofTexture(unittest.TestCase):
    def test_bounds_in_local_metres(self):
        e = plateau_pp.roof_texture_entry("r.jpg", [139.0, 35.0, 139.01, 35.01], [139.005, 35.005])
        self.assertAlmostEqual(e["bounds_m"][2] - e["bounds_m"][0], 0.01 * 111320.0 * 0.81915, delta=5)


class CacheDirs(unittest.TestCase):
    def test_gsi_tiles_go_to_the_shared_cache_and_the_box_specific_files_beside_the_output(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": root}):
            box, gsi = plateau_pp.cache_dirs(Path("/x/assets/buildings-a"))
        self.assertEqual(box, Path("/x/assets/buildings-a-cache"))
        self.assertEqual(gsi, Path(root) / "gsi")

    def test_explicit_directories_win(self):
        box, gsi = plateau_pp.cache_dirs(Path("/x/out"), cache=Path("/c"), gsi_cache=Path("/g"))
        self.assertEqual((box, gsi), (Path("/c"), Path("/g")))



class Build(unittest.TestCase):
    """build() end to end with every download and heavy step stubbed: what it calls, and what it writes."""

    def run_build(self, plateau=True, bake=True, footprints=()):
        out = Path(tempfile.mkdtemp()) / "buildings-x"
        out.mkdir()
        (out / "models").mkdir()
        if plateau:
            (out / "models" / "t.glb").write_bytes(b"glb")
            (out / "manifest.json").write_text(json.dumps({
                "center": [139.0, 35.0], "tiles": [{"glb": "models/t.glb", "rtc": [0, 0, 0], "ids": ["a", "b"]}]}))
        heights = {"a": {"lonlat": [139.0, 35.0], "height": 30.0}, "b": {"lonlat": [139.001, 35.0], "height": 6.0}}

        class Photo:
            def save(self, path, quality=None):
                Path(path).write_bytes(b"jpg")

        def proxy(footprints, bbox, out_dir, **kw):
            self.proxy_kw, self.proxy_footprints = kw, footprints
            m = json.loads((Path(out_dir) / "manifest.json").read_text())
            for kind in ("city-proxy", "city-shadow"):
                (Path(out_dir) / "models" / f"{kind}.glb").write_bytes(kind.encode())
                m["tiles"].append({"glb": f"models/{kind}.glb", "kind": kind, "frame": "enu", "ids": ["gsi/1"],
                                   "roof_texture": {"image": "roof-photo.jpg", "bounds_m": [-5, -5, 5, 5]}})
            m.update(tile_count=len(m["tiles"]), city_proxy_building_count=1)
            return m

        self.baked = []

        def bake_untextured(raw, rtc, ids, colours, photo, bounds):
            self.baked.append(("plateau", raw, ids, colours))
            return raw + b"-baked"

        def bake_proxy(raw, ids, photo, bounds_m):
            self.baked.append(("proxy", raw, ids, bounds_m))
            return raw + b"-baked"

        def no_tiles(*a, **kw):
            raise ValueError("no leaf content intersects the requested bbox")

        self.ortho = mock.MagicMock(side_effect=AssertionError("the z16 orthophoto is not used any more"))
        self.palette = mock.MagicMock(side_effect=AssertionError("its colours were overwritten unused"))
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": root}), \
                mock.patch.object(plateau_pp, "fetch_osm_buildings", return_value=[]) as self.osm, \
                mock.patch("geo.seasonal_ortho.fetch_gsi_ortho_mosaic", self.ortho), \
                mock.patch("buildings.building_appearance.apply_orthophoto_palette", self.palette), \
                mock.patch("buildings.gsi_footprints.fetch_gsi_buildings", return_value=list(footprints)) as self.gsi, \
                mock.patch("buildings.cell_heights.feature_heights", return_value=heights) as self.cal, \
                mock.patch("buildings.gsi_footprints.dem_sampler", return_value=lambda lon, lat: 0.0) as self.dem, \
                mock.patch("buildings.gsi_footprints.orthophoto_texture", return_value=(Photo(), [139.0, 35.0, 139.01, 35.01])), \
                mock.patch.object(gs, "extract_glb_feature_heights", return_value=heights), \
                mock.patch.object(gs, "extract_glb_feature_shapes", return_value={}), \
                mock.patch("buildings.city_proxy.build_city_proxy_tile", side_effect=proxy), \
                mock.patch("buildings.pp_bake.bake_untextured", side_effect=bake_untextured), \
                mock.patch("buildings.pp_bake.bake_proxy", side_effect=bake_proxy), \
                mock.patch("buildings.plateau_3d.prepare_tiles", side_effect=no_tiles):
            m = plateau_pp.build(out, [139.0, 35.0, 139.01, 35.01], bake=bake)
        return out, m

    def test_every_tile_but_the_shadow_is_baked_and_the_manifest_names_the_version(self):
        from buildings.city_proxy import wall_hex
        out, m = self.run_build()
        self.assertEqual([(k, raw) for k, raw, *_ in self.baked], [("plateau", b"glb"), ("proxy", b"city-proxy")])
        self.assertEqual(self.baked[0][3], [wall_hex("a", 30.0), wall_hex("b", 6.0)])
        self.assertEqual(self.baked[1][3], [-5, -5, 5, 5])
        self.assertEqual((out / "models" / "t.glb").read_bytes(), b"glb-baked")
        self.assertEqual((out / "models" / "city-shadow.glb").read_bytes(), b"city-shadow")
        self.assertEqual(m["plateau_pp"], {"version": plateau_pp.PLATEAU_PP_VERSION, "baked": True})
        self.assertEqual(m["tiles"][0]["bytes"], len(b"glb-baked"))

    def test_filled_in_heights_are_calibrated_on_the_whole_mesh_cells_of_the_footprints(self):
        from buildings import cell_heights, jis_mesh
        ring = [[139.0021, 35.0021], [139.0022, 35.0021], [139.0022, 35.0022], [139.0021, 35.0022], [139.0021, 35.0021]]
        foot = {"type": "Feature", "id": "gsi/1", "properties": {"vt_code": "3101"},
                "geometry": {"type": "Polygon", "coordinates": [ring]}}
        self.run_build(footprints=[foot])
        cell = jis_mesh.mesh3(139.0021, 35.0021)
        box = cell_heights.cells_box([cell])
        self.assertEqual(self.cal.call_args.args[1], box)        # PLATEAU read for the whole cell, not the box
        self.assertIn(box, [c.args[0] for c in self.gsi.call_args_list])
        self.assertEqual(list(self.proxy_kw["height_model"].models), [cell])

    def test_the_context_around_the_box_is_read_and_only_the_box_is_built(self):
        """A building near the edge is judged with what stands around it (OSM, GSI pieces across tile seams, the
        ground, PLATEAU's shadows), so it comes out as in a box around it; only the footprints touching the box
        are filled in."""
        def foot(i, lon):
            ring = [[lon, 35.005], [lon + 0.0001, 35.005], [lon + 0.0001, 35.0051], [lon, 35.0051], [lon, 35.005]]
            return {"type": "Feature", "id": f"gsi/{i}", "properties": {"vt_code": "3101"},
                    "geometry": {"type": "Polygon", "coordinates": [ring]}}
        inside, outside = foot(1, 139.005), foot(2, 139.0115)          # the second about 100 m east of the box
        self.run_build(footprints=[inside, outside])
        box = [139.0, 35.0, 139.01, 35.01]
        context = plateau_pp.grow(box, plateau_pp.CONTEXT_M)
        self.assertEqual(self.osm.call_args.args[0], context)
        self.assertEqual(self.gsi.call_args_list[0].args[0], context)
        self.assertEqual(self.dem.call_args.args[0], context)
        self.assertEqual(self.proxy_footprints, [inside])
        self.assertLess(context[0], box[0] - 0.003)

    def test_no_bake_leaves_the_look_to_the_renderer_as_before(self):
        out, m = self.run_build(bake=False)
        self.assertEqual(self.baked, [])
        self.assertEqual((out / "models" / "t.glb").read_bytes(), b"glb")
        self.assertNotIn("plateau_pp", m)

    def test_the_command_line_takes_no_bake(self):
        with mock.patch.object(plateau_pp, "build") as build:
            plateau_pp.main(["/tmp/x", "--bbox=1,2,3,4", "--no-bake"])
        self.assertIs(build.call_args.kwargs["bake"], False)

    def test_an_area_without_plateau_tiles_is_built_from_footprints_alone(self):
        out, m = self.run_build(plateau=False)
        self.assertEqual([t.get("kind") for t in m["tiles"]], ["city-proxy", "city-shadow"])
        np_close = [round(v, 9) for v in m["center"]]
        self.assertEqual(np_close, [139.005, 35.005])
        self.assertEqual(m["plateau_building_count"], 0)

    def test_no_orthophoto_mosaic_is_fetched_for_facade_colours(self):
        self.run_build()
        self.ortho.assert_not_called()
        self.palette.assert_not_called()

    def test_walls_get_a_colour_from_id_and_height_and_roofs_the_photo(self):
        from buildings.city_proxy import wall_hex
        out, m = self.run_build()
        self.assertEqual(m["tiles"][0]["facade_colors"], [wall_hex("a", 30.0), wall_hex("b", 6.0)])
        self.assertEqual(m["roof_texture"]["image"], "roof-photo.jpg")
        self.assertTrue((out / "roof-photo.jpg").exists())



class Cached(unittest.TestCase):
    """cached(): one finished PLATEAU++ per request under tmp/.cache/plateau-pp/v<version>/<key>/."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"GEO_VIDEO_CACHE": self.root})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []

        def build(out, bbox, tileset, cache=None, seed="plateau-pp", gsi_cache=None, bake=True):
            self.calls.append(Path(out))
            Path(out).mkdir(parents=True, exist_ok=True)
            (Path(out) / "manifest.json").write_text(json.dumps({"tiles": [], "plateau_pp": {"version": plateau_pp.PLATEAU_PP_VERSION}}))
            return {}
        self.build = mock.patch.object(plateau_pp, "build", side_effect=build)
        self.build.start()
        self.addCleanup(self.build.stop)

    def test_the_key_follows_the_request_and_ignores_float_noise(self):
        k = plateau_pp.cache_key([139.68, 35.688, 139.69, 35.696], plateau_pp.TOKYO_2025, "plateau-pp")
        self.assertEqual(k, plateau_pp.cache_key([139.6800000001, 35.688, 139.69, 35.696], plateau_pp.TOKYO_2025, "plateau-pp"))
        self.assertNotEqual(k, plateau_pp.cache_key([139.68, 35.688, 139.69, 35.697], plateau_pp.TOKYO_2025, "plateau-pp"))
        self.assertNotEqual(k, plateau_pp.cache_key([139.68, 35.688, 139.69, 35.696], plateau_pp.TOKYO_2025, "other"))

    def test_the_first_request_builds_under_the_version_and_the_next_reads_it(self):
        bbox = [139.68, 35.688, 139.69, 35.696]
        path = plateau_pp.cached(bbox)
        self.assertEqual(path.parent, Path(self.root) / "plateau-pp" / f"v{plateau_pp.PLATEAU_PP_VERSION}")
        self.assertTrue((path / "manifest.json").exists())
        self.assertEqual(json.loads((path / "request.json").read_text())["bbox"], bbox)
        self.assertEqual(plateau_pp.cached(bbox), path)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.calls[0].name.endswith(".part"))          # built aside, then moved into place

    def test_a_build_left_half_done_is_started_again(self):
        bbox = [139.68, 35.688, 139.69, 35.696]
        part = plateau_pp.cache_dir(bbox).with_name(plateau_pp.cache_dir(bbox).name + ".part")
        part.mkdir(parents=True)
        (part / "stale").write_text("x")
        path = plateau_pp.cached(bbox)
        self.assertFalse((path / "stale").exists())
        self.assertFalse(part.exists())

    def test_the_command_line_without_an_output_prints_the_cached_build(self):
        with mock.patch("builtins.print") as printed:
            plateau_pp.main(["--bbox=139.68,35.688,139.69,35.696"])
        self.assertEqual(Path(printed.call_args.args[0]), plateau_pp.cache_dir([139.68, 35.688, 139.69, 35.696]))


if __name__ == "__main__":
    unittest.main()
