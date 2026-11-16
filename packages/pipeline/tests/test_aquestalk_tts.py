import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support import import_pipeline

aquestalk_tts = import_pipeline("aquestalk_tts")


class AquesTalkTtsTests(unittest.TestCase):
    def test_speed_to_percent_clamps_to_aquestalk_range(self) -> None:
        self.assertEqual(aquestalk_tts.speed_to_percent(1.0), 100)
        self.assertEqual(aquestalk_tts.speed_to_percent(1.2), 120)
        self.assertEqual(aquestalk_tts.speed_to_percent(0.1), 50)
        self.assertEqual(aquestalk_tts.speed_to_percent(5.0), 300)

    def test_resolve_paths_validates_app_bundle_layout(self) -> None:
        with TemporaryDirectory() as tmp:
            app = Path(tmp) / "AquesTalkPlayer.app"
            fw = app / "Contents" / "Frameworks"
            res = app / "Contents" / "Resources"
            fw.mkdir(parents=True)
            res.mkdir(parents=True)
            (fw / "libAqKanji2Koe.dylib").write_bytes(b"")
            (fw / "libAquesTalk1-f1.dylib").write_bytes(b"")
            (res / "aqdic.bin").write_bytes(b"")

            k2k, dic, voice = aquestalk_tts.resolve_bundle_paths(app, "f1")
            self.assertEqual(k2k, fw / "libAqKanji2Koe.dylib")
            self.assertEqual(dic, res)
            self.assertEqual(voice, fw / "libAquesTalk1-f1.dylib")

            with self.assertRaises(FileNotFoundError):
                aquestalk_tts.resolve_bundle_paths(app, "f2")


if __name__ == "__main__":
    unittest.main()
