#!/usr/bin/env python3
"""Synthesize Yukkuri (AquesTalk1) WAV audio via an installed AquesTalkPlayer.app.

Usage:
  python3 packages/pipeline/narration/aquestalk_tts.py --voice f1 --speed 1.0 --out out.wav --text "こんにちは"
"""
from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path

DEFAULT_APP_DIR = Path("/Applications/AquesTalkPlayer.app")


def speed_to_percent(speed: float) -> int:
    """Convert a multiplier (1.0 = normal) to AquesTalk's 50..300 percentage."""
    return max(50, min(300, round(speed * 100)))


def resolve_bundle_paths(app_dir: str | Path, voice_id: str) -> tuple[Path, Path, Path]:
    """Locate AqKanji2Koe, dictionary directory, and AquesTalk1 voice dylib inside app_dir."""
    root = Path(app_dir)
    frameworks = root / "Contents" / "Frameworks"
    resources = root / "Contents" / "Resources"
    k2k = frameworks / "libAqKanji2Koe.dylib"
    dic = resources / "aqdic.bin"
    voice = frameworks / f"libAquesTalk1-{voice_id}.dylib"
    for target, label in ((k2k, "libAqKanji2Koe.dylib"), (dic, "aqdic.bin"), (voice, f"libAquesTalk1-{voice_id}.dylib")):
        if not target.is_file():
            raise FileNotFoundError(f"AquesTalk asset not found ({label}): {target}")
    return k2k, resources, voice


def synthesize(
    text: str,
    out_wav: str | Path,
    voice_id: str = "f1",
    speed: float = 1.0,
    app_dir: str | Path | None = None,
) -> Path:
    """Synthesize text to a WAV file using AquesTalkPlayer's arm64 dylibs."""
    resolved_app = Path(app_dir or os.environ.get("AQUESTALK_APP_DIR") or DEFAULT_APP_DIR)
    k2k_path, dic_dir, voice_path = resolve_bundle_paths(resolved_app, voice_id)

    k2k = ctypes.CDLL(str(k2k_path))
    aq1 = ctypes.CDLL(str(voice_path))

    k2k.AqKanji2Koe_Create.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    k2k.AqKanji2Koe_Create.restype = ctypes.c_void_p
    k2k.AqKanji2Koe_Convert.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    k2k.AqKanji2Koe_Convert.restype = ctypes.c_int
    k2k.AqKanji2Koe_Release.argtypes = [ctypes.c_void_p]

    aq1.AquesTalk_Synthe_Utf8.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    aq1.AquesTalk_Synthe_Utf8.restype = ctypes.POINTER(ctypes.c_ubyte)
    aq1.AquesTalk_FreeWave.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]

    err = ctypes.c_int(0)
    handle = k2k.AqKanji2Koe_Create(str(dic_dir).encode("utf-8"), ctypes.byref(err))
    if not handle:
        raise RuntimeError(f"AqKanji2Koe_Create failed with code {err.value}")
    try:
        buf_size = max(4096, len(text.encode("utf-8")) * 8)
        koe_buf = ctypes.create_string_buffer(buf_size)
        rc = k2k.AqKanji2Koe_Convert(handle, text.encode("utf-8"), koe_buf, buf_size)
        if rc != 0:
            raise RuntimeError(f"AqKanji2Koe_Convert failed with code {rc}")
        koe_bytes = koe_buf.value
    finally:
        k2k.AqKanji2Koe_Release(handle)

    wav_size = ctypes.c_int(0)
    wav_ptr = aq1.AquesTalk_Synthe_Utf8(koe_bytes, speed_to_percent(speed), ctypes.byref(wav_size))
    if not wav_ptr or wav_size.value <= 0:
        raise RuntimeError(f"AquesTalk_Synthe_Utf8 failed (code/size={wav_size.value}) for: {text}")
    try:
        out_path = Path(out_wav)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(bytes(wav_ptr[: wav_size.value]))
        return out_path
    finally:
        aq1.AquesTalk_FreeWave(wav_ptr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Synthesize WAV with AquesTalkPlayer.app")
    parser.add_argument("--voice", default="f1", help="AquesTalk1 voice ID (e.g. f1, f2)")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier (1.0 = normal)")
    parser.add_argument("--out", required=True, help="Output WAV path")
    parser.add_argument("--text", required=True, help="Input Japanese text")
    parser.add_argument("--app", default=None, help="Path to AquesTalkPlayer.app")
    args = parser.parse_args(argv)
    synthesize(args.text, args.out, voice_id=args.voice, speed=args.speed, app_dir=args.app)


if __name__ == "__main__":
    main()
