#!/usr/bin/env python3
"""Compose and concatenate all 17 clips with overlays and master audio."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
MANIFEST = PROJECT / "manifest.json"
MASTER_AUDIO = PROJECT / "audio" / "generated" / "master_mix.wav"


def run_cmd(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def ensure_clip_composed(clip_id: str, mode: str, force: bool = False) -> Path:
    base = PROJECT / "out" / mode / "clips" / clip_id
    if mode == "preview":
        mp4 = base / f"{clip_id}.mp4"
        if not mp4.exists():
            raise FileNotFoundError(f"Missing preview clip: {mp4}")
        return mp4

    # final mode: compose map.mp4 + overlay.mov (+ optional extra overlay)
    map_mp4 = base / "map" / "map.mp4"
    ov_mov = base / "overlay" / "overlay.mov"
    if not map_mp4.exists():
        raise FileNotFoundError(f"Missing map layer: {map_mp4}")
    if not ov_mov.exists():
        raise FileNotFoundError(f"Missing overlay layer: {ov_mov}")

    composed = base / f"{clip_id}_composed.mp4"
    extra_ov = PROJECT / "overlays" / "generated" / f"{clip_id}_extra.mov"

    if composed.exists() and not force:
        # Rebuild if inputs are newer
        newest_in = max(map_mp4.stat().st_mtime, ov_mov.stat().st_mtime,
                        extra_ov.stat().st_mtime if extra_ov.exists() else 0)
        if composed.stat().st_mtime >= newest_in:
            return composed

    if extra_ov.exists():
        run_cmd([
            "ffmpeg", "-y",
            "-i", str(map_mp4),
            "-i", str(ov_mov),
            "-i", str(extra_ov),
            "-filter_complex", "[0:v][1:v]overlay=format=auto:shortest=1[v1];[v1][2:v]overlay=format=auto:shortest=1,format=yuv420p[v]",
            "-map", "[v]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
            "-r", "30", str(composed),
        ])
    else:
        run_cmd([
            "ffmpeg", "-y",
            "-i", str(map_mp4),
            "-i", str(ov_mov),
            "-filter_complex", "[0:v][1:v]overlay=format=auto:shortest=1,format=yuv420p[v]",
            "-map", "[v]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
            "-r", "30", str(composed),
        ])
    return composed


def main() -> None:
    parser = argparse.ArgumentParser(description="Build combined video from clips")
    parser.add_argument("--mode", choices=["preview", "final"], default="preview")
    parser.add_argument("--version", default="v0.1.0")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-audio", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    clip_paths = [ensure_clip_composed(c["id"], args.mode, force=args.force) for c in manifest["clips"]]

    out_dir = PROJECT / "out" / args.mode
    out_dir.mkdir(parents=True, exist_ok=True)
    concat_txt = out_dir / "concat.txt"
    concat_txt.write_text("".join(f"file '{p}'\n" for p in clip_paths), encoding="utf-8")

    video_only = out_dir / f"plateau-award-2026-{args.mode}-{args.version}.silent.mp4"
    final_mp4 = out_dir / f"plateau-award-2026-{args.mode}-{args.version}.mp4"

    # Re-encode stream cleanly during concat to guarantee uniform 30fps (or 15fps) & timestamps
    fps = "15" if args.mode == "preview" else "30"
    crf = "22" if args.mode == "preview" else "18"
    run_cmd([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", crf, "-preset", "medium",
        "-r", fps, "-movflags", "+faststart", str(video_only),
    ])

    if args.no_audio or not MASTER_AUDIO.exists():
        video_only.rename(final_mp4)
    else:
        run_cmd([
            "ffmpeg", "-y",
            "-i", str(video_only),
            "-i", str(MASTER_AUDIO),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(final_mp4),
        ])
        video_only.unlink(missing_ok=True)

    print(f"\nBuilt {final_mp4}", flush=True)


if __name__ == "__main__":
    main()
