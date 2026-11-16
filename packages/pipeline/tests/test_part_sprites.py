import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from support import import_pipeline

part_sprites = import_pipeline("part_sprites")


def make_png(path: Path, size: tuple[int, int], box: tuple[int, int, int, int], color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    for x in range(box[0], box[2]):
        for y in range(box[1], box[3]):
            im.putpixel((x, y), color)
    im.save(path)


class PartSpritesTests(unittest.TestCase):
    def _create_sample_parts(self, root: Path) -> dict:
        size = (100, 100)
        make_png(root / "体" / "体_00.png", size, (20, 20, 80, 90), (240, 220, 200, 255))
        make_png(root / "目" / "目_00.png", size, (35, 40, 65, 50), (20, 20, 20, 255))
        make_png(root / "目" / "目_00.0.png", size, (35, 44, 65, 46), (20, 20, 20, 255))
        make_png(root / "口" / "口_closed.png", size, (42, 65, 58, 69), (120, 40, 40, 255))
        make_png(root / "口" / "口_open.png", size, (40, 62, 60, 74), (220, 60, 70, 255))
        make_png(root / "他" / "帽子.png", size, (10, 10, 90, 30), (30, 30, 40, 255))
        return {
            "order": ["体", "目", "口", "他"],
            "width": 120,
            "base": {"体": "体_00", "目": "目_00"},
            "blink": {"目": "目_00.0"},
            "faces": {
                "normal": {"mouth_open": "口_open", "mouth_closed": "口_closed"},
                "smile": {"select": {"他": "帽子"}, "mouth_open": "口_open", "mouth_closed": "口_closed"},
            },
        }

    def test_resolve_part_path_finds_png_and_rejects_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "体" / "体_00.png"
            make_png(target, (10, 10), (0, 0, 5, 5), (255, 0, 0, 255))
            self.assertEqual(part_sprites.resolve_part_path(root, "体", "体_00"), target)
            self.assertEqual(part_sprites.resolve_part_path(root, "体", "体_00.png"), target)
            with self.assertRaises(FileNotFoundError):
                part_sprites.resolve_part_path(root, "体", "missing")

    def test_render_writes_all_variants_and_sheet_in_order(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            parts_dir = root / "parts"
            out_dir = root / "out"
            cfg = self._create_sample_parts(parts_dir)
            made = part_sprites.render(parts_dir, cfg, out_dir)
            self.assertEqual(
                made,
                [
                    "normal_o_o.png", "normal_o_c.png", "normal_c_o.png", "normal_c_c.png",
                    "smile_o_o.png", "smile_o_c.png", "smile_c_o.png", "smile_c_c.png",
                ],
            )
            self.assertTrue((out_dir / "sheet.png").is_file())
            with Image.open(out_dir / "smile_o_o.png") as im:
                self.assertEqual(im.width, 120)
                # Top-left pixel inside the hat area should reflect the hat layer drawn over body.
                self.assertGreater(im.getpixel((0, 0))[3], 0)

    def test_render_uses_union_bbox_and_min_width_padding(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            parts_dir = root / "parts"
            out_dir = root / "out"
            cfg = self._create_sample_parts(parts_dir)
            cfg["min_width"] = 120
            cfg["width"] = 120
            part_sprites.render(parts_dir, cfg, out_dir)
            sizes = set()
            for name in ("normal_o_o.png", "smile_o_o.png"):
                with Image.open(out_dir / name) as im:
                    sizes.add(im.size)
            self.assertEqual(len(sizes), 1)

    def test_render_rejects_empty_faces(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "faces"):
                part_sprites.render(Path(tmp), {"order": ["体"], "faces": {}}, Path(tmp) / "out")


if __name__ == "__main__":
    unittest.main()
