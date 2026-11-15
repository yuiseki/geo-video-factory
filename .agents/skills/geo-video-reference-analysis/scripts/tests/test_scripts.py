import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import refstats  # noqa: E402
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


if __name__ == '__main__':
    unittest.main()
