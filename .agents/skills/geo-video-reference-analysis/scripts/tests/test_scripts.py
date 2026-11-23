import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import refstats  # noqa: E402
import shot_plan  # noqa: E402
import transcript  # noqa: E402

ROLLING = """WEBVTT
Kind: captions
Language: ja

00:00:00.599 --> 00:00:03.230 align:start position:0%

日本<00:00:00.840><c>の</c><00:00:01.040><c>周り</c>

00:00:03.230 --> 00:00:03.240 align:start position:0%
日本の周り


00:00:03.240 --> 00:00:06.510 align:start position:0%
日本の周り
の海<00:00:03.399><c>から</c>

00:01:06.510 --> 00:01:06.520 align:start position:0%
の海から

"""

CLEAN = """WEBVTT

00:00:00.840 --> 00:00:05.840
お台場。豊洲。
築地。

00:00:06.860 --> 00:00:07.920
この5つの場所。
"""


class TranscriptTest(unittest.TestCase):
    def test_rolling_auto_captions_are_deduplicated(self):
        lines = transcript.parse(ROLLING)
        self.assertEqual([t for _, t in lines], ['日本の周り', 'の海から'])
        self.assertEqual(lines[0][0], 0.599)
        self.assertEqual(lines[1][0], 3.24)

    def test_clean_captions_keep_every_line(self):
        lines = transcript.parse(CLEAN)
        self.assertEqual([t for _, t in lines], ['お台場。豊洲。', '築地。', 'この5つの場所。'])

    def test_chars_per_second_ignores_spaces(self):
        self.assertAlmostEqual(transcript.chars_per_second([(0, 'あい う'), (1, 'え')], 2.0), 2.0)

    def test_timestamp_format(self):
        self.assertEqual(transcript.mmss(3725.4), '62:05')


class RefStatsTest(unittest.TestCase):
    INFO = {
        'id': 'abc', 'title': 't', 'channel': 'c', 'duration': 600,
        'view_count': 100000, 'like_count': 500, 'comment_count': 50,
        'channel_follower_count': 2000, 'timestamp': 1_000_000, 'epoch': 1_000_000 + 10 * 86400,
        'upload_date': '20260101',
        'chapters': [{'start_time': 0, 'end_time': 200, 'title': 'a'},
                     {'start_time': 200, 'end_time': 600, 'title': 'b'}],
        'tags': ['x', 'y'],
    }

    def test_ratios(self):
        s = refstats.summarise(self.INFO)
        self.assertEqual(s['views_per_follower'], 50.0)
        self.assertAlmostEqual(s['like_rate'], 0.005)
        self.assertAlmostEqual(s['comment_rate'], 0.0005)
        self.assertEqual(s['days_since_publish'], 10.0)
        self.assertEqual(s['views_per_day'], 10000.0)
        self.assertEqual(s['chapters'], 2)
        self.assertEqual(s['mean_chapter_seconds'], 300.0)
        self.assertEqual(s['published'], '2026-01-01')

    def test_hidden_counts_stay_missing(self):
        info = dict(self.INFO, channel_follower_count=None, like_count=None)
        s = refstats.summarise(info)
        self.assertIsNone(s['views_per_follower'])
        self.assertIsNone(s['like_rate'])

    def test_reads_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d, 'a.info.json')
            p.write_text(json.dumps(self.INFO))
            self.assertEqual(refstats.load(p)['id'], 'abc')


class ShotPlanTest(unittest.TestCase):
    MOTION_TSV = (
        't\tscale_per_s\tdx_per_s\tdy_per_s\tinliers\tlabel\n'
        '0.5\t1.01000\t0.0\t0.0\t50\tzoom_in\n'
        '1.0\t1.01200\t0.0\t0.0\t48\tzoom_in\n'
        '1.5\t1.00000\t0.0\t0.0\t40\tstatic\n'
        '2.5\t1.00000\t-10.0\t0.0\t45\tpan_right\n'
        '3.0\t1.00000\t-12.0\t0.0\t42\tpan_right\n'
        '5.5\t1.00000\t0.0\t0.0\t35\tstatic\n'
    )
    TRANSCRIPT_TXT = (
        '00:00 最初の問いを立てます。\n'
        '00:02 地図で場所を確認します。\n'
        '00:05 まとめに入ります。\n'
    )

    def test_build_intervals_merges_noise_cuts_and_bounds_duration(self):
        # 2.15 is within min_shot=0.5s of 2.0, so it is ignored as noise
        intervals = shot_plan.build_intervals([0.0, 2.0, 2.15, 5.0, 12.0], duration=10.0, min_shot=0.5)
        self.assertEqual(intervals, [(0.0, 2.0), (2.0, 5.0), (5.0, 10.0)])

    def test_build_intervals_without_cuts_returns_single_shot(self):
        self.assertEqual(shot_plan.build_intervals([], duration=30.0), [(0.0, 30.0)])

    def test_parse_motion_and_transcript(self):
        motion_rows = shot_plan.parse_motion_tsv(self.MOTION_TSV)
        self.assertEqual(len(motion_rows), 6)
        self.assertEqual(motion_rows[0], (0.5, 'zoom_in'))
        captions = shot_plan.parse_transcript_txt(self.TRANSCRIPT_TXT)
        self.assertEqual(captions[1], (2.0, '地図で場所を確認します。'))

    def test_build_shots_aggregates_motion_captions_and_chapters(self):
        motion_rows = shot_plan.parse_motion_tsv(self.MOTION_TSV)
        captions = shot_plan.parse_transcript_txt(self.TRANSCRIPT_TXT)
        chapters = [
            {'start_time': 0.0, 'end_time': 5.0, 'title': '導入'},
            {'start_time': 5.0, 'end_time': 10.0, 'title': 'まとめ'},
        ]
        shots = shot_plan.build_shots(
            cuts=[2.0, 5.0],
            duration=10.0,
            motion_rows=motion_rows,
            captions=captions,
            chapters=chapters,
        )
        self.assertEqual(len(shots), 3)
        self.assertEqual(shots[0]['id'], 'S001')
        self.assertEqual(shots[0]['dominant_motion'], 'zoom_in')
        self.assertEqual(shots[0]['chapter'], '導入')
        self.assertIn('最初の問い', shots[0]['caption'])
        self.assertEqual(shots[1]['dominant_motion'], 'pan_right')
        self.assertEqual(shots[2]['chapter'], 'まとめ')
        self.assertEqual(shots[2]['dominant_motion'], 'static')

    def test_summarise_shots_reports_pace_and_distribution(self):
        shots = shot_plan.build_shots(
            cuts=[2.0, 5.0],
            duration=10.0,
            motion_rows=shot_plan.parse_motion_tsv(self.MOTION_TSV),
            captions=shot_plan.parse_transcript_txt(self.TRANSCRIPT_TXT),
        )
        summary = shot_plan.summarise_shots(shots, duration=10.0)
        self.assertEqual(summary['shot_count'], 3)
        self.assertAlmostEqual(summary['median_shot_seconds'], 3.0)
        self.assertAlmostEqual(summary['cuts_per_min'], 12.0)
        self.assertEqual(summary['motion_counts']['zoom_in'], 1)
        self.assertEqual(summary['motion_counts']['pan_right'], 1)

    def test_render_markdown_contains_four_layers_and_routes(self):
        shots = shot_plan.build_shots(
            cuts=[2.0, 5.0],
            duration=10.0,
            motion_rows=shot_plan.parse_motion_tsv(self.MOTION_TSV),
            captions=shot_plan.parse_transcript_txt(self.TRANSCRIPT_TXT),
        )
        md = shot_plan.render_markdown(shots, shot_plan.summarise_shots(shots, 10.0))
        self.assertIn('## Layer 1:', md)
        self.assertIn('## Layer 2:', md)
        self.assertIn('## Layer 3:', md)
        self.assertIn('## Layer 4:', md)
        self.assertIn('S001', md)
        self.assertIn('renderer標準', md)
        self.assertIn('pipeline事前生成', md)
        self.assertIn('素材収集', md)
        self.assertIn('要新規実装', md)


if __name__ == '__main__':
    unittest.main()
