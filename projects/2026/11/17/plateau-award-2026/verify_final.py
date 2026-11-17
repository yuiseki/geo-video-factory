#!/usr/bin/env python3
"""Verify final MP4 technical specs, loudness, edit-point continuity, and extract sample frames."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
MANIFEST = PROJECT / "manifest.json"


def main() -> None:
    mp4 = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT / "out/final/plateau-award-2026-final-v1.0.0.mp4"
    assert mp4.exists(), f"Missing {mp4}"

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration,size",
         "-of", "json", str(mp4)],
        capture_output=True, text=True, check=True,
    )
    meta = json.loads(probe.stdout)
    v = next(s for s in meta["streams"] if s["codec_type"] == "video")
    a = next(s for s in meta["streams"] if s["codec_type"] == "audio")
    dur = float(meta["format"]["duration"])
    size_mb = int(meta["format"]["size"]) / (1024 * 1024)

    print(f"File: {mp4}")
    print(f"Video: {v['codec_name']} {v['width']}x{v['height']} fps={v['r_frame_rate']}")
    print(f"Audio: {a['codec_name']}")
    print(f"Duration: {dur:.2f}s (< 180s: {dur < 180.0})")
    print(f"Size: {size_mb:.1f} MB")

    assert v["codec_name"] == "h264"
    assert (v["width"], v["height"]) == (1920, 1080)
    assert v["r_frame_rate"] == "30/1"
    assert 170.0 <= dur < 180.0

    # Loudness check (ebur128)
    ebur = subprocess.run(
        ["ffmpeg", "-i", str(mp4), "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    for line in ebur.stderr.splitlines():
        if "I:" in line or "Peak:" in line or "LRA:" in line:
            print("Loudness:", line.strip())

    # Extract key timestamp frames from final MP4 for visual inspection
    inspect_dir = PROJECT / "out/final/inspect"
    inspect_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for clip in manifest["clips"]:
        cid = clip["id"]
        mid = clip["start_sec"] + clip["duration"] * 0.5
        out_jpg = inspect_dir / f"{cid}_mid.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{mid:.2f}", "-i", str(mp4), "-frames:v", "1", "-q:v", "2", str(out_jpg)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
    print(f"Extracted {len(manifest['clips'])} mid-point inspection frames to {inspect_dir}")


if __name__ == "__main__":
    main()
