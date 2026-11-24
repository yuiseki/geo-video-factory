import contextlib
import io
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from narration import ambient_bgm as bgm  # noqa: E402

SR = bgm.SR


def read_wav(path):
    with wave.open(str(path), "rb") as f:
        params = (f.getnchannels(), f.getsampwidth(), f.getframerate(), f.getnframes())
        return params, np.frombuffer(f.readframes(f.getnframes()), "<i2").reshape(-1, 2)


class NoteTests(unittest.TestCase):
    def test_hz_reads_octaves_sharps_and_flats_from_concert_pitch(self):
        self.assertAlmostEqual(bgm.hz("A4"), 440.0)
        self.assertAlmostEqual(bgm.hz("A3"), 220.0)
        self.assertAlmostEqual(bgm.hz("C#5"), 440.0 * 2 ** (4 / 12))
        self.assertAlmostEqual(bgm.hz("Bb3"), bgm.hz("A#3"))
        self.assertAlmostEqual(bgm.hz("C4"), 440.0 * 2 ** (-9 / 12))

    def test_every_chord_and_bell_note_is_readable(self):
        for root, notes in bgm.DAY + bgm.NIGHT:
            self.assertLess(bgm.hz(root), min(bgm.hz(n) for n in notes))
        self.assertEqual(sorted(bgm.BELLS_DAY, key=bgm.hz), bgm.BELLS_DAY)
        self.assertEqual(sorted(bgm.BELLS_NIGHT, key=bgm.hz), bgm.BELLS_NIGHT)


class BuildingBlockTests(unittest.TestCase):
    def test_envelope_rises_from_silence_holds_one_and_falls_back(self):
        e = bgm.envelope(SR, 0.25, 0.5)
        self.assertEqual(len(e), SR)
        self.assertEqual(e[0], 0.0)
        self.assertTrue(np.all(e[SR // 4: SR // 2] == 1.0))
        self.assertLess(e[-1], 1e-6)
        self.assertTrue(np.all(np.diff(e[: SR // 4]) > 0))
        self.assertTrue(np.all(np.diff(e[SR // 2:]) < 0))

    def test_bell_starts_at_zero_and_dies_away(self):
        b = bgm.bell(880.0, seconds=2.0)
        self.assertEqual(len(b), 2 * SR)
        self.assertEqual(b[0], 0.0)
        self.assertLess(np.abs(b[-SR // 2:]).max(), 0.3 * np.abs(b[: SR // 2]).max())

    def test_pad_is_stereo_silent_at_both_ends_and_repeats_for_the_same_random_state(self):
        a = bgm.pad(220.0, 8.0, np.random.default_rng(1))
        b = bgm.pad(220.0, 8.0, np.random.default_rng(1))
        self.assertEqual(a.shape, (8 * SR, 2))
        self.assertTrue(np.array_equal(a, b))
        self.assertTrue(np.all(a[0] == 0.0))
        self.assertLess(np.abs(a[-1]).max(), 1e-6)
        self.assertFalse(np.allclose(a[:, 0], a[:, 1]))  # the two voices sit on different sides

    def test_add_mixes_a_sound_in_at_its_start_time(self):
        mix = np.zeros(SR)
        bgm.add(mix, 0.5, np.ones(10))
        self.assertEqual((mix[SR // 2 - 1], mix[SR // 2], mix[SR // 2 + 9], mix[SR // 2 + 10]), (0.0, 1.0, 1.0, 0.0))

    def test_add_cuts_what_falls_outside_the_piece(self):
        mix = np.zeros(SR)
        bgm.add(mix, 1.0 - 4 / SR, np.arange(1.0, 11.0))     # the tail runs past the end
        self.assertEqual(mix[-4:].tolist(), [1.0, 2.0, 3.0, 4.0])
        mix = np.zeros(SR)
        bgm.add(mix, -4 / SR, np.arange(1.0, 11.0))          # the head begins before zero
        self.assertEqual(mix[:7].tolist(), [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 0.0])
        mix = np.zeros(SR)
        bgm.add(mix, 2.0, np.ones(10))                       # entirely after the end
        self.assertEqual(np.abs(mix).max(), 0.0)


class NightBoundaryTests(unittest.TestCase):
    def test_night_begins_on_the_nearest_chord_boundary(self):
        self.assertEqual(bgm.night_boundary(15.0), 16.0)
        self.assertEqual(bgm.night_boundary(82.0), 80.0)
        self.assertEqual(bgm.night_boundary(0.0), 0.0)

    def test_a_time_exactly_between_two_boundaries_goes_to_the_even_numbered_chord(self):
        # Python rounds halves to even, so the tie does not always go the same way.
        self.assertEqual(bgm.night_boundary(4.0), 0.0)
        self.assertEqual(bgm.night_boundary(12.0), 16.0)
        self.assertEqual(bgm.night_boundary(20.0), 16.0)


class ScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.day = bgm.score(24.0, np.random.default_rng(7))
        cls.night = bgm.score(24.0, np.random.default_rng(7), night_from=15.0)

    def test_layers_are_stereo_and_as_long_as_the_piece(self):
        for layer in self.day:
            self.assertEqual(layer.shape, (24 * SR, 2))

    def test_bells_wait_for_the_second_chord(self):
        bells = self.day[2]
        self.assertEqual(np.abs(bells[: 8 * SR]).max(), 0.0)
        self.assertGreater(np.abs(bells[8 * SR:]).max(), 0.0)

    def test_night_from_leaves_the_notes_alone_until_the_night_chord_swells_in(self):
        # The night chord at 16 s starts its pad 1.5 s early; nothing before that may differ.
        cut = int(14.5 * SR)
        for day, night in zip(self.day, self.night):
            self.assertTrue(np.array_equal(day[:cut], night[:cut]))

    def test_night_from_changes_pads_and_bass_after_the_boundary(self):
        pads_d, bass_d, _ = self.day
        pads_n, bass_n, _ = self.night
        self.assertFalse(np.allclose(pads_d[16 * SR:], pads_n[16 * SR:]))
        self.assertFalse(np.allclose(bass_d[16 * SR:], bass_n[16 * SR:]))
        # the bass swells in 0.5 s before its chord, later than the pads
        self.assertTrue(np.array_equal(bass_d[: int(15.5 * SR)], bass_n[: int(15.5 * SR)]))


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.day = bgm.render(16.0)
        cls.night = bgm.render(16.0, night_from=8.0)

    def test_length_is_seconds_times_the_sample_rate_in_stereo(self):
        self.assertEqual(self.day.shape, (16 * SR, 2))
        self.assertEqual(bgm.render(7.5).shape, (int(7.5 * SR), 2))

    def test_peak_sits_three_decibels_below_full_scale(self):
        self.assertAlmostEqual(20 * np.log10(np.abs(self.day).max()), -3.0, places=9)
        self.assertAlmostEqual(20 * np.log10(np.abs(self.night).max()), -3.0, places=9)

    def test_piece_fades_in_from_silence_and_out_to_silence(self):
        self.assertTrue(np.all(self.day[0] == 0.0))
        self.assertLess(np.abs(self.day[-1]).max(), 1e-6)
        first = np.abs(self.day[: SR // 10]).max()
        self.assertLess(first, 0.05 * np.abs(self.day[4 * SR: 8 * SR]).max())

    def test_same_arguments_give_the_same_samples(self):
        self.assertTrue(np.array_equal(self.day, bgm.render(16.0)))

    def test_seed_changes_the_piece(self):
        self.assertFalse(np.allclose(self.day, bgm.render(16.0, seed=8)))

    def test_night_from_changes_the_finished_mix_from_its_first_second(self):
        # Not only the chords change: the noise bed and the reverb tails are drawn from the same random stream
        # after the notes, and the peak is normalised over the whole piece, so no stretch stays sample-identical.
        self.assertFalse(np.allclose(self.day[SR // 2: SR], self.night[SR // 2: SR]))
        self.assertFalse(np.allclose(self.day[12 * SR:], self.night[12 * SR:]))

    def test_refuses_a_piece_shorter_than_its_fade_out(self):
        with self.assertRaisesRegex(ValueError, "at least 7"):
            bgm.render(6.9)


class WavAndCliTests(unittest.TestCase):
    def test_write_wav_stores_48k_16_bit_stereo_truncated_towards_zero(self):
        mix = np.array([[0.0, 1.0], [-1.0, 0.5], [0.25, -0.25]])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.wav"
            bgm.write_wav(path, mix)
            params, samples = read_wav(path)
        self.assertEqual(params, (2, 2, 48000, 3))
        self.assertEqual(samples.tolist(), [[0, 32767], [-32767, 16383], [8191, -8191]])

    def test_main_writes_the_rendered_piece_and_reports_its_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bgm.wav"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = bgm.main([str(path), "16", "--night-from=8"])
            params, samples = read_wav(path)
        self.assertEqual(code, 0)
        self.assertEqual(params, (2, 2, 48000, 16 * SR))
        self.assertTrue(np.array_equal(samples, (bgm.render(16.0, night_from=8.0) * 32767).astype("<i2")))
        self.assertIn(f"{path}: 16.0 s, peak -3.0 dBFS, rms -", stdout.getvalue())

    def test_main_passes_the_seed_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bgm.wav"
            with contextlib.redirect_stdout(io.StringIO()):
                bgm.main([str(path), "8", "--seed=8"])
            _, samples = read_wav(path)
        self.assertTrue(np.array_equal(samples, (bgm.render(8.0, seed=8) * 32767).astype("<i2")))

    def test_main_refuses_an_option_it_does_not_know(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bgm.wav"
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                bgm.main([str(path), "8", "--night=4"])
            self.assertNotEqual(raised.exception.code, 0)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
