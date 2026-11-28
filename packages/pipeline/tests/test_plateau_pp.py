import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from buildings import glb_spatial as gs
from buildings import plateau_pp

from test_glb_strip import plain_glb


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
    """build(): the box is assembled from the per-tile store (pp_tiles); what each tile holds is tested there."""

    def test_build_assembles_the_box_from_the_store(self):
        with mock.patch("buildings.pp_tiles.assemble", return_value={"tile_count": 0, "plateau_building_count": 0,
                        "city_proxy_building_count": 0, "removed_buildings": []}) as assemble:
            plateau_pp.build(Path("/tmp/box"), [139.0, 35.0, 139.01, 35.01])
        out, bbox, tileset, gsi, seed = assemble.call_args.args
        self.assertEqual((out, bbox, tileset, seed), (Path("/tmp/box"), [139.0, 35.0, 139.01, 35.01],
                                                      plateau_pp.TOKYO_2025, "plateau-pp"))

    def test_no_bake_is_refused_loudly(self):
        with self.assertRaises(SystemExit):
            plateau_pp.build(Path("/tmp/box"), [139.0, 35.0, 139.01, 35.01], bake=False)


class Cached(unittest.TestCase):
    """cached(): one box (manifest and links) per request under tmp/.cache/plateau-pp/v<version>/boxes/<key>/."""

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
        self.assertEqual(path.parent, Path(self.root) / "plateau-pp" / f"v{plateau_pp.PLATEAU_PP_VERSION}" / "boxes")
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

    def test_a_box_another_live_process_is_building_is_left_alone(self):
        """Two photo_solve runs that ask for the same box: neither throws away the other's half-built directory."""
        bbox = [139.68, 35.688, 139.69, 35.696]
        final = plateau_pp.cache_dir(bbox)
        theirs = final.with_name(f"{final.name}.{os.getppid()}.part")      # a process that is alive
        theirs.mkdir(parents=True)
        (theirs / "half").write_text("x")
        path = plateau_pp.cached(bbox)
        self.assertTrue((theirs / "half").exists())
        self.assertTrue((path / "manifest.json").exists())
        self.assertNotEqual(self.calls[0], theirs)

    def test_the_liveness_check_never_signals_a_process_on_windows(self):
        """On Windows os.kill(pid, 0) terminates the process; the check must not call it there."""
        with mock.patch.object(plateau_pp.os, "name", "nt"), mock.patch.object(plateau_pp.os, "kill") as kill:
            try:
                plateau_pp._alive(str(os.getpid()))
            except AttributeError:        # no ctypes.windll off Windows: what matters is that kill was not called
                pass
        kill.assert_not_called()

    def test_a_dead_process_part_is_thrown_away(self):
        bbox = [139.68, 35.688, 139.69, 35.696]
        final = plateau_pp.cache_dir(bbox)
        dead = final.with_name(f"{final.name}.99999999.part")
        dead.mkdir(parents=True)
        plateau_pp.cached(bbox)
        self.assertFalse(dead.exists())

    def test_a_box_finished_by_another_process_meanwhile_is_taken_and_ours_dropped(self):
        bbox = [139.68, 35.688, 139.69, 35.696]
        final = plateau_pp.cache_dir(bbox)
        self.build.stop()

        def build(out, *a, **k):          # while we build, the other process moves its box into place
            self.calls.append(Path(out))
            final.mkdir(parents=True)
            (final / "manifest.json").write_text("{}")
            (final / "theirs").write_text("x")
            Path(out).mkdir(parents=True, exist_ok=True)
            (Path(out) / "manifest.json").write_text("{}")
        with mock.patch.object(plateau_pp, "build", side_effect=build):
            path = plateau_pp.cached(bbox)
        self.build.start()
        self.assertEqual(path, final)
        self.assertTrue((final / "theirs").exists())
        self.assertFalse(self.calls[0].exists())

    def test_the_command_line_without_an_output_prints_the_cached_build(self):
        with mock.patch("builtins.print") as printed:
            plateau_pp.main(["--bbox=139.68,35.688,139.69,35.696"])
        self.assertEqual(Path(printed.call_args.args[0]), plateau_pp.cache_dir([139.68, 35.688, 139.69, 35.696]))


if __name__ == "__main__":
    unittest.main()
