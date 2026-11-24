import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video import title_cards as tc  # noqa: E402

SIZE = (1280, 720)
W, H = SIZE
BACKGROUND = (6, 7, 10)


def bundled_font(role, size):
    """Pillow's built-in face, so the tests need no font installed on the machine."""
    return ImageFont.load_default(size)


def bbox(mask):
    """(left, top, right, bottom) of the true pixels, right and bottom inclusive."""
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def bright(image):
    """The text itself in an overlay: white and nearly opaque (the shadow is dark, the rest transparent)."""
    a = np.asarray(image)
    return (a[..., :3].min(axis=2) > 160) & (a[..., 3] > 160)


def differs_from_background(image):
    return np.any(np.asarray(image) != np.array(BACKGROUND, np.uint8), axis=2)


class FontTests(unittest.TestCase):
    def test_paths_default_to_noto_cjk_and_follow_the_environment(self):
        self.assertEqual(tc.font_paths({}), tc.DEFAULT_FONT_PATHS)
        self.assertIn("NotoSerifCJK-Bold", tc.DEFAULT_FONT_PATHS["serif"])
        self.assertIn("NotoSansCJK-Regular", tc.DEFAULT_FONT_PATHS["sans"])
        paths = tc.font_paths({"FONT_SERIF": "/fonts/a.ttf", "FONT_SANS": "/fonts/b.ttf"})
        self.assertEqual(paths, {"serif": "/fonts/a.ttf", "sans": "/fonts/b.ttf"})

    def test_loader_opens_the_file_of_the_role_at_the_asked_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "face.ttf"
            path.write_bytes(ImageFont.load_default(10).font_bytes)
            fonts = tc.truetype_fonts({"serif": str(path), "sans": str(path)})
            self.assertEqual(fonts("serif", 31).size, 31)
            self.assertEqual(fonts("sans", 12).size, 12)

    def test_loader_names_the_missing_file_and_the_variable_that_moves_it(self):
        fonts = tc.truetype_fonts({"serif": "/nonexistent/serif.ttc", "sans": "/nonexistent/sans.ttc"})
        with self.assertRaisesRegex(FileNotFoundError, r"/nonexistent/sans\.ttc.*FONT_SANS"):
            fonts("sans", 12)

    def test_loader_refuses_a_role_it_has_no_file_for(self):
        with self.assertRaises(KeyError):
            tc.truetype_fonts({"serif": "a", "sans": "b"})("mono", 12)


class TextHelperTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.font = bundled_font("sans", 20)

    def test_spaced_returns_where_the_text_ends_including_the_last_gap(self):
        plain = sum(self.draw.textlength(ch, font=self.font) for ch in "ABC")
        end = tc.spaced(self.draw, (10, 5), "ABC", self.font, (255, 255, 255, 255), spacing=4.0)
        self.assertAlmostEqual(end, 10 + plain + 3 * 4.0)

    def test_width_does_not_count_a_gap_after_the_last_letter(self):
        plain = sum(self.draw.textlength(ch, font=self.font) for ch in "ABC")
        self.assertAlmostEqual(tc.width(self.draw, "ABC", self.font, spacing=4.0), plain + 2 * 4.0)
        self.assertAlmostEqual(tc.width(self.draw, "ABC", self.font), plain)

    def test_spacing_moves_the_letters_apart(self):
        tc.spaced(self.draw, (10, 5), "II", self.font, (255, 255, 255, 255), spacing=0.0)
        tight = bbox(np.asarray(self.image)[..., 3] > 0)
        wide_image = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
        tc.spaced(ImageDraw.Draw(wide_image), (10, 5), "II", self.font, (255, 255, 255, 255), spacing=30.0)
        wide = bbox(np.asarray(wide_image)[..., 3] > 0)
        self.assertEqual(wide[0], tight[0])
        self.assertEqual(wide[2] - tight[2], 30)

    def test_shadow_keeps_the_text_and_puts_a_dark_halo_around_it(self):
        self.draw.rectangle([90, 25, 110, 35], fill=(255, 255, 255, 255))
        out = np.asarray(tc.with_shadow(self.image))
        self.assertEqual(out.shape, (60, 200, 4))
        self.assertEqual(out[30, 100].tolist(), [255, 255, 255, 255])
        halo = out[30, 84]                                  # 6 px left of the rectangle
        self.assertEqual(halo[:3].tolist(), [0, 0, 0])
        self.assertGreater(halo[3], 0)
        self.assertEqual(out[5, 5, 3], 0)                   # far away: still transparent


class PlaceLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.label = tc.place_label("Ginza", "Ginza 4-chome", SIZE, bundled_font)

    def test_is_a_transparent_overlay_of_the_frame_size(self):
        self.assertEqual((self.label.mode, self.label.size), ("RGBA", SIZE))
        alpha = np.asarray(self.label)[..., 3]
        self.assertEqual(alpha[: H // 2].max(), 0)          # nothing in the upper half
        self.assertEqual(alpha[:, W // 2:].max(), 0)        # a short name stays in the left half

    def test_text_starts_at_the_left_margin_in_the_lower_third(self):
        left, top, right, bottom = bbox(bright(self.label))
        self.assertGreaterEqual(left, round(W * 0.05))
        self.assertLessEqual(left, round(W * 0.05) + 4)
        self.assertGreaterEqual(top, round(H * 0.70))
        self.assertLess(bottom, H * 0.90)

    def test_a_rule_separates_the_two_names(self):
        x, y = round(W * 0.05) + 4, round(H * 0.70) + H * 0.108
        rule = np.asarray(self.label)[round(y) + 1, x + 2: round(x + H * 0.09) - 2]
        self.assertTrue(np.all(rule[:, :3] > 200))
        self.assertTrue(np.all(rule[:, 3] > 200))

    def test_english_name_is_drawn_in_capitals(self):
        lower = tc.place_label("Ginza", "ginza", SIZE, bundled_font)
        upper = tc.place_label("Ginza", "GINZA", SIZE, bundled_font)
        self.assertTrue(np.array_equal(np.asarray(lower), np.asarray(upper)))


class CreditLineTests(unittest.TestCase):
    def test_is_a_transparent_overlay_with_text_only_in_the_bottom_strip(self):
        credit = tc.credit_line("Photo: someone (CC0)", SIZE, bundled_font)
        self.assertEqual((credit.mode, credit.size), ("RGBA", SIZE))
        left, top, right, bottom = bbox(bright(credit))
        self.assertGreaterEqual(top, H - round(H * 0.055))
        self.assertLess(bottom, H)
        self.assertEqual(np.asarray(credit)[: int(H * 0.8), :, 3].max(), 0)

    def test_text_ends_at_the_right_margin_whatever_its_length(self):
        margin = W - round(W * 0.03)
        for text in ("Photo: A", "Photo: someone with a longer name / Somewhere (CC0)  3D: PLATEAU"):
            right = bbox(bright(tc.credit_line(text, SIZE, bundled_font)))[2]
            self.assertLessEqual(right, margin, text)
            self.assertGreaterEqual(right, margin - 3, text)

    def test_longer_text_grows_to_the_left(self):
        short = bbox(bright(tc.credit_line("Photo: A", SIZE, bundled_font)))
        long = bbox(bright(tc.credit_line("Photo: A and many more words", SIZE, bundled_font)))
        self.assertLess(long[0], short[0])


class TitleCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = tc.title_card("TOKYO", "WITHOUT PEOPLE", SIZE, bundled_font)
        cls.ink = differs_from_background(cls.card)

    def test_is_an_opaque_dark_frame(self):
        self.assertEqual((self.card.mode, self.card.size), ("RGB", SIZE))
        for xy in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1)):
            self.assertEqual(self.card.getpixel(xy), BACKGROUND)

    def test_both_lines_are_centred(self):
        for rows in (slice(int(H * 0.36), int(H * 0.55)), slice(int(H * 0.56), int(H * 0.70))):
            left, _, right, _ = bbox(self.ink[rows])
            self.assertAlmostEqual((left + right) / 2, W / 2, delta=3)

    def test_main_title_sits_above_a_smaller_subtitle(self):
        _, top, _, bottom = bbox(self.ink)
        self.assertGreaterEqual(top, int(H * 0.36))
        self.assertLess(bottom, H * 0.65)
        main = bbox(self.ink[int(H * 0.36): int(H * 0.55)])
        sub = bbox(self.ink[int(H * 0.56): int(H * 0.70)])
        self.assertGreater(main[3] - main[1], 2 * (sub[3] - sub[1]))
        self.assertFalse(self.ink[int(H * 0.52): int(H * 0.56)].any())   # a clear gap between the lines


class EndCardTests(unittest.TestCase):
    LABEL, TEXT = (150, 158, 172), (232, 232, 228)

    def colour(self, card, rgb):
        return np.all(np.asarray(card) == np.array(rgb, np.uint8), axis=2)

    def test_block_height_counts_the_heading_full_lines_and_short_gaps(self):
        self.assertAlmostEqual(tc.end_card_block_height(["a", "", "b"], 1000), 95 + 47 + 20 + 47)
        self.assertAlmostEqual(tc.end_card_block_height([], 1000), 95)

    def test_labels_sit_at_the_left_margin_and_their_text_in_a_second_column(self):
        card = tc.end_card("HEADING", ["Ginza\tSomeone, 2020, CC0"], SIZE, bundled_font)
        self.assertEqual((card.mode, card.size), ("RGB", SIZE))
        self.assertEqual(card.getpixel((0, 0)), BACKGROUND)
        label = bbox(self.colour(card, self.LABEL))
        self.assertGreaterEqual(label[0], int(W * 0.08))
        self.assertLess(label[2], W * 0.25)
        # the heading shares the text colour, so look at the row of the line only
        text = self.colour(card, self.TEXT)
        text[: label[1] - 2] = False
        self.assertGreaterEqual(bbox(text)[0], int(W * 0.25))

    def test_a_line_without_a_tab_starts_at_the_left_margin_in_the_text_colour(self):
        card = tc.end_card("", ["A plain sentence."], SIZE, bundled_font)
        self.assertFalse(self.colour(card, self.LABEL).any())
        left = bbox(self.colour(card, self.TEXT))[0]
        self.assertGreaterEqual(left, int(W * 0.08))
        self.assertLess(left, W * 0.08 + 6)

    def test_block_is_centred_so_more_lines_lift_the_heading(self):
        few = bbox(differs_from_background(tc.end_card("HEADING", ["a\tb"], SIZE, bundled_font)))
        many = bbox(differs_from_background(tc.end_card("HEADING", ["a\tb"] * 9, SIZE, bundled_font)))
        self.assertLess(many[1], few[1])
        self.assertGreater(many[3], few[3])
        self.assertAlmostEqual((many[1] + many[3]) / 2, H / 2, delta=H * 0.04)

    def test_an_empty_line_leaves_a_smaller_gap_than_a_line_of_text(self):
        def last_row(lines):
            card = tc.end_card("", lines, (640, 720), bundled_font)
            return bbox(self.colour(card, self.TEXT))
        # the blocks differ in height, and with it in where they start; compare the distance first to last line
        gap = last_row(["x", "", "x"])
        full = last_row(["x", "x", "x"])
        self.assertAlmostEqual((full[3] - full[1]) - (gap[3] - gap[1]), 720 * (0.047 - 0.02), delta=1.5)

    def test_refuses_a_block_that_does_not_fit_the_frame(self):
        tc.end_card("HEADING", ["a\tb"] * 17, SIZE, bundled_font)        # 0.095 + 17 * 0.047 = 0.894
        with self.assertRaisesRegex(ValueError, r"overflows.*0\.94"):
            tc.end_card("HEADING", ["a\tb"] * 18, SIZE, bundled_font)    # 0.941


if __name__ == "__main__":
    unittest.main()
