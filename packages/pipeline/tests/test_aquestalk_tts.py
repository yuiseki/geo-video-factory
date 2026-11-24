import ctypes
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from support import import_pipeline

aquestalk_tts = import_pipeline("narration.aquestalk_tts")


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


def make_app_bundle(root: Path, voices: tuple[str, ...] = ("f1",)) -> Path:
    app = root / "AquesTalkPlayer.app"
    frameworks = app / "Contents" / "Frameworks"
    resources = app / "Contents" / "Resources"
    frameworks.mkdir(parents=True)
    resources.mkdir(parents=True)
    (frameworks / "libAqKanji2Koe.dylib").write_bytes(b"")
    (resources / "aqdic.bin").write_bytes(b"")
    for voice in voices:
        (frameworks / f"libAquesTalk1-{voice}.dylib").write_bytes(b"")
    return app


class FakeAquesTalk:
    """Pure-Python stand-ins for the two dylibs, following the C calling convention synthesize() uses."""

    def __init__(self, *, wav: bytes = b"RIFFfake-wav", create_error: int = 0, convert_rc: int = 0, synth_error: int = 0):
        self.wav = wav
        self.create_error = create_error
        self.convert_rc = convert_rc
        self.synth_error = synth_error
        self.loaded: list[str] = []
        self.events: list[str] = []
        self.dictionary_dir = None
        self.converted_text = None
        self.synth_args = None
        self._wav_buffer = (ctypes.c_ubyte * len(wav))(*wav)
        self.k2k = Mock(spec=["AqKanji2Koe_Create", "AqKanji2Koe_Convert", "AqKanji2Koe_Release"])
        self.k2k.AqKanji2Koe_Create.side_effect = self._create
        self.k2k.AqKanji2Koe_Convert.side_effect = self._convert
        self.k2k.AqKanji2Koe_Release.side_effect = lambda handle: self.events.append("release")
        self.aq1 = Mock(spec=["AquesTalk_Synthe_Utf8", "AquesTalk_FreeWave"])
        self.aq1.AquesTalk_Synthe_Utf8.side_effect = self._synthesize
        self.aq1.AquesTalk_FreeWave.side_effect = lambda pointer: self.events.append("free")

    def cdll(self, path: str):
        self.loaded.append(path)
        return self.k2k if "AqKanji2Koe" in path else self.aq1

    def _create(self, dictionary_dir, err_ref):
        self.dictionary_dir = dictionary_dir
        if self.create_error:
            err_ref._obj.value = self.create_error
            return None
        return 0x1234

    def _convert(self, handle, text, koe_buffer, size):
        self.converted_text = text
        self.events.append("convert")
        if self.convert_rc:
            return self.convert_rc
        koe_buffer.value = b"koe:" + text
        return 0

    def _synthesize(self, koe, percent, size_ref):
        self.synth_args = (koe, percent)
        self.events.append("synth")
        if self.synth_error:
            size_ref._obj.value = self.synth_error
            return ctypes.POINTER(ctypes.c_ubyte)()
        size_ref._obj.value = len(self.wav)
        return ctypes.cast(self._wav_buffer, ctypes.POINTER(ctypes.c_ubyte))


class AquesTalkSynthesizeTests(unittest.TestCase):
    def synthesize(self, fake: FakeAquesTalk, *args, **kwargs):
        with patch.object(aquestalk_tts.ctypes, "CDLL", side_effect=fake.cdll):
            return aquestalk_tts.synthesize(*args, **kwargs)

    def test_synthesize_writes_the_wav_and_passes_text_dictionary_and_speed_to_the_libraries(self) -> None:
        with TemporaryDirectory() as tmp:
            app = make_app_bundle(Path(tmp), voices=("f1", "f2"))
            out = Path(tmp) / "voice" / "line-001.wav"
            fake = FakeAquesTalk(wav=b"RIFF\x00\x01\x02\xffdata")
            result = self.synthesize(fake, "こんにちは", out, voice_id="f2", speed=1.25, app_dir=app)

            self.assertEqual(result, out)
            self.assertEqual(out.read_bytes(), b"RIFF\x00\x01\x02\xffdata")
            frameworks = app / "Contents" / "Frameworks"
            self.assertEqual(fake.loaded, [str(frameworks / "libAqKanji2Koe.dylib"), str(frameworks / "libAquesTalk1-f2.dylib")])
            self.assertEqual(fake.dictionary_dir, str(app / "Contents" / "Resources").encode("utf-8"))
            self.assertEqual(fake.converted_text, "こんにちは".encode("utf-8"))
            self.assertEqual(fake.synth_args, (b"koe:" + "こんにちは".encode("utf-8"), 125))
            # Both native resources are handed back: the converter handle and the wave buffer.
            self.assertEqual(fake.events, ["convert", "release", "synth", "free"])

    def test_app_dir_falls_back_to_environment_variable_then_default(self) -> None:
        with TemporaryDirectory() as tmp:
            env_app = make_app_bundle(Path(tmp) / "from-env")
            default_app = make_app_bundle(Path(tmp) / "default")
            out = Path(tmp) / "out.wav"
            with patch.object(aquestalk_tts, "DEFAULT_APP_DIR", default_app):
                fake = FakeAquesTalk()
                with patch.dict(os.environ, {"AQUESTALK_APP_DIR": str(env_app)}):
                    self.synthesize(fake, "テスト", out)
                self.assertTrue(fake.loaded[0].startswith(str(env_app)))

                fake = FakeAquesTalk()
                with patch.dict(os.environ):
                    os.environ.pop("AQUESTALK_APP_DIR", None)
                    self.synthesize(fake, "テスト", out)
                self.assertTrue(fake.loaded[0].startswith(str(default_app)))

    def test_missing_bundle_fails_before_any_library_is_loaded(self) -> None:
        with TemporaryDirectory() as tmp:
            fake = FakeAquesTalk()
            with self.assertRaisesRegex(FileNotFoundError, "libAqKanji2Koe.dylib"):
                self.synthesize(fake, "テスト", Path(tmp) / "out.wav", app_dir=Path(tmp) / "Nowhere.app")
            self.assertEqual(fake.loaded, [])

    def test_dictionary_open_failure_reports_the_library_error_code(self) -> None:
        with TemporaryDirectory() as tmp:
            app = make_app_bundle(Path(tmp))
            out = Path(tmp) / "out.wav"
            fake = FakeAquesTalk(create_error=101)
            with self.assertRaisesRegex(RuntimeError, "AqKanji2Koe_Create failed with code 101"):
                self.synthesize(fake, "テスト", out, app_dir=app)
            self.assertFalse(out.exists())
            self.assertEqual(fake.events, [])

    def test_conversion_failure_releases_the_converter_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            app = make_app_bundle(Path(tmp))
            out = Path(tmp) / "out.wav"
            fake = FakeAquesTalk(convert_rc=105)
            with self.assertRaisesRegex(RuntimeError, "AqKanji2Koe_Convert failed with code 105"):
                self.synthesize(fake, "テスト", out, app_dir=app)
            self.assertEqual(fake.events, ["convert", "release"])
            self.assertFalse(out.exists())

    def test_synthesis_failure_names_the_text_and_writes_nothing(self) -> None:
        with TemporaryDirectory() as tmp:
            app = make_app_bundle(Path(tmp))
            out = Path(tmp) / "out.wav"
            fake = FakeAquesTalk(synth_error=-3)
            with self.assertRaisesRegex(RuntimeError, r"AquesTalk_Synthe_Utf8 failed \(code/size=-3\) for: よめないもじ"):
                self.synthesize(fake, "よめないもじ", out, app_dir=app)
            self.assertFalse(out.exists())

    def test_long_text_gets_a_conversion_buffer_larger_than_the_4096_byte_minimum(self) -> None:
        with TemporaryDirectory() as tmp:
            app = make_app_bundle(Path(tmp))
            text = "あ" * 400  # 1200 UTF-8 bytes
            fake = FakeAquesTalk()
            self.synthesize(fake, text, Path(tmp) / "out.wav", app_dir=app)
            buffer_size = fake.k2k.AqKanji2Koe_Convert.call_args.args[3]
            self.assertGreaterEqual(buffer_size, len(text.encode("utf-8")) * 2)
            self.assertGreater(buffer_size, 4096)
            self.assertEqual(len(fake.k2k.AqKanji2Koe_Convert.call_args.args[2]), buffer_size)

    def test_cli_forwards_arguments_to_synthesize(self) -> None:
        with patch.object(aquestalk_tts, "synthesize") as synthesize:
            aquestalk_tts.main(["--voice", "f2", "--speed", "0.8", "--out", "line.wav", "--text", "こんにちは", "--app", "Some.app"])
            synthesize.assert_called_once_with("こんにちは", "line.wav", voice_id="f2", speed=0.8, app_dir="Some.app")
            synthesize.reset_mock()
            aquestalk_tts.main(["--out", "line.wav", "--text", "やあ"])
            synthesize.assert_called_once_with("やあ", "line.wav", voice_id="f1", speed=1.0, app_dir=None)


if __name__ == "__main__":
    unittest.main()
