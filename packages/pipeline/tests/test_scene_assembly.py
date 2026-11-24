import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scene_assembly as sa  # noqa: E402

FF = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]


def bundled_font(role, size):
    return ImageFont.load_default(size)


def small_plan(size=(160, 90), fps=5):
    return {
        "size": list(size), "fps": fps, "crossfade": 1.0,
        "title": {"ja": "TOKYO", "en": "WITHOUT PEOPLE", "seconds": 2},
        "scenes": [
            {"name": "day_a", "ja": "Ginza", "en": "Ginza 4-chome", "credit": "Photo: A (CC0)"},
            {"name": "night_b", "ja": "Shibuya", "en": "Shibuya, 7 p.m.", "credit": "Photo: B (CC0)",
             "night": True, "frames_dir": "frames"},
        ],
        "credits": {"seconds": 3, "heading": "Tokyo", "lines": ["Ginza\tA, 2020, CC0", "", "Made by a program."]},
    }


def write_frames(directory, count, size, colour):
    directory.mkdir(parents=True)
    for i in range(count):
        Image.new("RGB", size, (colour[0], colour[1], 10 * i)).save(directory / f"{i:04d}.png")


def write_scenes(root, plan, frames_per_scene=20):
    for k, scene in enumerate(plan["scenes"]):
        directory = root / scene["name"] / scene.get("frames_dir", "f_mac")
        write_frames(directory, frames_per_scene, tuple(plan["size"]), (200 - 150 * k, 90, 0))


class TimelineTests(unittest.TestCase):
    # title 5 s, eight scenes of 14 s, credits 12 s, 1 s crossfades: the published 120 s cut
    DURATIONS = [5] + [336 / 24] * 8 + [12]

    def test_each_clip_starts_one_crossfade_before_the_previous_one_ends(self):
        starts = sa.clip_starts(self.DURATIONS, 1.0)
        self.assertEqual(starts[0], 0.0)
        self.assertEqual(starts[1:9], [4.0 + 13.0 * (k - 1) for k in range(1, 9)])
        self.assertEqual(starts[9], 108.0)

    def test_total_length_loses_one_crossfade_per_join(self):
        self.assertEqual(sa.total_length(self.DURATIONS, 1.0), 120.0)
        self.assertEqual(sa.total_length([5], 1.0), 5)
        self.assertEqual(sa.total_length([2, 4, 4, 3], 0.5), 11.5)

    def test_xfade_offsets_are_the_starts_of_every_clip_after_the_first(self):
        self.assertEqual(sa.xfade_offsets(self.DURATIONS, 1.0), sa.clip_starts(self.DURATIONS, 1.0)[1:])
        self.assertEqual(sa.xfade_offsets([2, 4, 3], 0.5), [1.5, 5.0])
        self.assertEqual(sa.xfade_offsets([5], 1.0), [])

    def test_night_starts_with_the_first_scene_marked_night(self):
        scenes = [{"name": "a"}, {"name": "b", "night": False}, {"name": "c", "night": True}, {"name": "d", "night": True}]
        self.assertEqual(sa.night_start(scenes, [4.0, 17.0, 30.0, 43.0]), 30.0)
        starts = sa.clip_starts(self.DURATIONS, 1.0)[1:9]
        self.assertEqual(sa.night_start([{}] * 6 + [{"night": True}] * 2, starts), 82.0)

    def test_night_start_is_none_when_no_scene_is_marked(self):
        self.assertIsNone(sa.night_start([{"name": "a"}, {"name": "b"}], [4.0, 17.0]))

    def test_night_start_refuses_lists_of_different_lengths(self):
        with self.assertRaises(ValueError):
            sa.night_start([{"night": True}], [4.0, 17.0])


class CommandTests(unittest.TestCase):
    def test_still_command_loops_the_image_for_its_seconds(self):
        cmd = sa.still_command(Path("w/title.png"), 5, Path("w/00_title.mp4"), fps=24)
        self.assertEqual(cmd, [*FF, "-loop", "1", "-t", "5", "-i", "w/title.png", "-vf", "fps=24,format=yuv420p",
                               "-c:v", "libx264", "-crf", "12", "-preset", "medium", "w/00_title.mp4"])

    def test_still_command_fades_in_from_zero_and_out_at_the_end(self):
        vf = sa.still_command(Path("a.png"), 5, Path("a.mp4"), fps=24, fade_in=1.2)
        self.assertEqual(vf[vf.index("-vf") + 1], "fps=24,format=yuv420p,fade=t=in:st=0:d=1.2")
        vf = sa.still_command(Path("a.png"), 12, Path("a.mp4"), fps=24, fade_out=2.0)
        self.assertEqual(vf[vf.index("-vf") + 1], "fps=24,format=yuv420p,fade=t=out:st=10.0:d=2.0")

    def test_still_command_refuses_a_fade_longer_than_the_clip(self):
        with self.assertRaisesRegex(ValueError, "fade"):
            sa.still_command(Path("a.png"), 1, Path("a.mp4"), fps=24, fade_out=2.0)

    def test_scene_filter_graph_fades_the_label_in_and_out_and_keeps_the_credit(self):
        self.assertEqual(
            sa.scene_filter_graph(14.0),
            "[1]format=rgba,fade=t=in:st=1.2:d=1.0:alpha=1,fade=t=out:st=7.0:d=1.2:alpha=1[l];"
            "[2]format=rgba,fade=t=in:st=1.2:d=1.0:alpha=1[c];[0][l]overlay[a];[a][c]overlay,format=yuv420p")

    def test_label_leaves_earlier_in_a_scene_shorter_than_ten_seconds(self):
        self.assertIn("fade=t=out:st=5.0:d=1.2", sa.scene_filter_graph(8.0))
        self.assertIn("fade=t=out:st=7.0:d=1.2", sa.scene_filter_graph(10.0))

    def test_scene_filter_graph_refuses_a_scene_too_short_for_its_label(self):
        # ffmpeg rejects a negative fade start; say which scene length is the problem instead.
        with self.assertRaisesRegex(ValueError, "3 s"):
            sa.scene_filter_graph(2.9)

    def test_scene_command_reads_the_numbered_frames_under_two_looped_overlays(self):
        cmd = sa.scene_command(Path("s/ginza/f_mac"), 336, Path("w/02_label.png"), Path("w/02_credit.png"),
                               Path("w/02_ginza.mp4"), fps=24)
        self.assertEqual(cmd, [
            *FF, "-framerate", "24", "-start_number", "0", "-i", "s/ginza/f_mac/%04d.png",
            "-loop", "1", "-t", "14.0", "-i", "w/02_label.png", "-loop", "1", "-t", "14.0", "-i", "w/02_credit.png",
            "-filter_complex", sa.scene_filter_graph(14.0), "-frames:v", "336",
            "-c:v", "libx264", "-crf", "12", "-preset", "medium", "w/02_ginza.mp4"])

    def test_xfade_filter_graph_chains_every_clip_onto_the_result_so_far(self):
        graph, last = sa.xfade_filter_graph([5, 14.0, 12], 1.0)
        self.assertEqual(graph, "[0:v][1:v]xfade=transition=fade:duration=1.0:offset=4.0000[v1];"
                                "[v1][2:v]xfade=transition=fade:duration=1.0:offset=17.0000[v2]")
        self.assertEqual(last, "v2")

    def test_xfade_filter_graph_needs_two_clips(self):
        with self.assertRaisesRegex(ValueError, "two clips"):
            sa.xfade_filter_graph([5], 1.0)

    def test_join_command_feeds_every_clip_and_encodes_the_last_label(self):
        clips = [Path("w/00_title.mp4"), Path("w/01_a.mp4"), Path("w/99_credits.mp4")]
        cmd = sa.join_command(clips, [5, 14.0, 12], 1.0, Path("w/video.mp4"), fps=24, crf="18")
        graph, _ = sa.xfade_filter_graph([5, 14.0, 12], 1.0)
        self.assertEqual(cmd, [
            *FF, "-i", "w/00_title.mp4", "-i", "w/01_a.mp4", "-i", "w/99_credits.mp4", "-filter_complex", graph,
            "-map", "[v2]", "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", "24",
            "w/video.mp4"])

    def test_join_command_refuses_clips_and_durations_that_do_not_pair_up(self):
        with self.assertRaises(ValueError):
            sa.join_command([Path("a.mp4"), Path("b.mp4")], [5, 14.0, 12], 1.0, Path("v.mp4"), fps=24, crf="18")

    def test_mux_command_copies_the_video_and_keeps_the_music_uncompressed_for_mastering(self):
        cmd = sa.mux_command(Path("w/video.mp4"), Path("w/bgm.wav"), Path("w/mixed.mov"))
        self.assertEqual(cmd, [*FF, "-i", "w/video.mp4", "-i", "w/bgm.wav", "-map", "0:v", "-map", "1:a",
                               "-c:v", "copy", "-c:a", "pcm_s16le", "-shortest", "w/mixed.mov"])


class SceneFramesTests(unittest.TestCase):
    def test_finds_the_numbered_frames_in_order_in_the_default_or_named_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_frames(root / "a" / "f_mac", 3, (16, 10), (1, 2))
            write_frames(root / "b" / "other", 2, (16, 10), (1, 2))
            (root / "a" / "f_mac" / "notes.png").write_bytes(b"")      # not a frame: no leading digit
            a = sa.scene_frames(root, {"name": "a"}, (16, 10))
            b = sa.scene_frames(root, {"name": "b", "frames_dir": "other"}, (16, 10))
        self.assertEqual([p.name for p in a], ["0000.png", "0001.png", "0002.png"])
        self.assertEqual([p.parent.name for p in b], ["other", "other"])

    def test_refuses_a_scene_without_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "no frames for ghost"):
                sa.scene_frames(Path(tmp), {"name": "ghost"}, (16, 10))

    def test_refuses_frames_of_another_size_than_the_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_frames(Path(tmp) / "a" / "f_mac", 1, (16, 10), (1, 2))
            with self.assertRaisesRegex(ValueError, r"a is not 32 x 18"):
                sa.scene_frames(Path(tmp), {"name": "a"}, (32, 18))


class RefusalTests(unittest.TestCase):
    """What stops an assembly before any encoding starts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = small_plan()
        write_scenes(self.root / "scenes", self.plan, frames_per_scene=2)

    def assemble(self, work="work", out="out.mp4"):
        return sa.assemble(self.plan, self.root / "scenes", self.root / work, self.root / out, fonts=bundled_font,
                           log=lambda line: None)

    def test_refuses_to_overwrite_an_existing_output(self):
        (self.root / "out.mp4").write_bytes(b"earlier version")
        with self.assertRaisesRegex(FileExistsError, "out.mp4 exists: give a new version"):
            self.assemble()
        self.assertEqual((self.root / "out.mp4").read_bytes(), b"earlier version")
        self.assertFalse((self.root / "work").exists())

    def test_refuses_to_reuse_an_existing_work_directory(self):
        (self.root / "work").mkdir()
        (self.root / "work" / "keep.txt").write_text("x")
        with self.assertRaisesRegex(FileExistsError, "work"):
            self.assemble()
        self.assertEqual([p.name for p in (self.root / "work").iterdir()], ["keep.txt"])
        self.assertFalse((self.root / "out.mp4").exists())

    def test_missing_frames_stop_the_run_before_the_work_directory_is_made(self):
        self.plan["scenes"].append({"name": "ghost", "ja": "x", "en": "x", "credit": "x"})
        with self.assertRaisesRegex(FileNotFoundError, "ghost"):
            self.assemble()
        self.assertFalse((self.root / "work").exists())

    def test_an_overflowing_end_card_stops_the_run_before_the_work_directory_is_made(self):
        self.plan["credits"]["lines"] = ["a\tb"] * 18
        with self.assertRaisesRegex(ValueError, "overflows"):
            self.assemble()
        self.assertFalse((self.root / "work").exists())

    def test_main_reports_an_existing_output_in_one_line_and_fails(self):
        (self.root / "out.mp4").write_bytes(b"earlier version")
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(self.plan))
        with self.assertRaises(SystemExit) as raised:
            sa.main([str(plan_path), str(self.root / "scenes"), str(self.root / "work"), str(self.root / "out.mp4")])
        self.assertIn("out.mp4 exists: give a new version", str(raised.exception.code))

    def test_main_refuses_an_option_it_does_not_know(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            sa.main(["plan.json", "scenes", "work", "out.mp4", "--quality=18"])
        self.assertEqual(raised.exception.code, 2)


class EndToEndTests(unittest.TestCase):
    """Two tiny scenes through real ffmpeg, by the command line: title 2 s + 4 s + 4 s + credits 3 s, 1 s
    crossfades, so 10 s; the second scene is the night one and starts at 4 s."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        plan = small_plan()
        write_scenes(root / "scenes", plan)
        (root / "plan.json").write_text(json.dumps(plan))
        # The command line takes its fonts from the environment; point it at Pillow's built-in face.
        font = root / "face.ttf"
        font.write_bytes(ImageFont.load_default(10).font_bytes)
        cls.work, cls.out = root / "work", root / "v1.mp4"
        stdout = io.StringIO()
        with mock.patch.dict("os.environ", {"FONT_SERIF": str(font), "FONT_SANS": str(font)}), \
                contextlib.redirect_stdout(stdout):
            cls.code = sa.main([str(root / "plan.json"), str(root / "scenes"), str(cls.work), str(cls.out), "--crf=30"])
        cls.stdout = stdout.getvalue()
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels,nb_frames",
             "-of", "json", str(cls.out)], check=True, capture_output=True, text=True)
        cls.probe = json.loads(probe.stdout)

    def stream(self, kind):
        return next(s for s in self.probe["streams"] if s["codec_type"] == kind)

    def test_output_lasts_as_long_as_the_timeline(self):
        self.assertEqual(self.code, 0)
        self.assertAlmostEqual(float(self.probe["format"]["duration"]), 10.0, delta=0.25)

    def test_video_keeps_the_plan_size_and_frame_rate(self):
        video = self.stream("video")
        self.assertEqual((video["codec_name"], video["width"], video["height"], video["r_frame_rate"]),
                         ("h264", 160, 90, "5/1"))
        self.assertEqual(int(video["nb_frames"]), 50)

    def test_audio_is_the_mastered_music(self):
        audio = self.stream("audio")
        self.assertEqual((audio["codec_name"], audio["sample_rate"], audio["channels"]), ("aac", "48000", 2))
        self.assertEqual(len(self.probe["streams"]), 2)

    def test_work_directory_keeps_every_intermediate_file(self):
        self.assertEqual({p.name for p in self.work.iterdir()}, {
            "00_title.mp4", "01_day_a.mp4", "01_credit.png", "01_label.png", "02_credit.png", "02_label.png",
            "02_night_b.mp4", "99_credits.mp4", "bgm.wav", "credits.png", "mixed.mov", "title.png", "video.mp4"})
        with Image.open(self.work / "01_label.png") as label, Image.open(self.work / "title.png") as title:
            self.assertEqual(label.mode, "RGBA")
            self.assertEqual(title.size, (160, 90))

    def test_progress_names_each_scene_its_start_and_the_night(self):
        self.assertIn("day_a: 20 frames, starts at 1.0 s", self.stdout)
        self.assertIn("night_b: 20 frames, starts at 4.0 s", self.stdout)
        self.assertIn("bgm.wav: 10.0 s", self.stdout)
        self.assertIn("v1.mp4: 10.0 s, night from 4.0, loudness before mastering {", self.stdout)


if __name__ == "__main__":
    unittest.main()
