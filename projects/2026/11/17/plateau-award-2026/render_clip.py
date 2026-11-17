#!/usr/bin/env python3
"""Render one or more clips independently (preview or final map/overlay layers)."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
REPO = PROJECT.parents[4]
RENDER_JS = REPO / "packages/renderer/dist/src/render.js"
MANIFEST = PROJECT / "manifest.json"


def run_cmd(cmd: list[str], cwd: Path = REPO) -> None:
    env = {k: v for k, v in os.environ.items() if k != "NODE_V8_COVERAGE"}
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def render_single(clip_id: str, mode: str, layer: str, stills: str | None) -> None:
    shot_file = PROJECT / "shots" / f"{clip_id}.json"
    if not shot_file.exists():
        raise FileNotFoundError(f"Shot file not found: {shot_file}")

    size = "640x360" if mode == "preview" else "1920x1080"
    fps = "15" if mode == "preview" else "30"
    base_out = PROJECT / "out" / mode / "clips" / clip_id

    if stills:
        out_dir = base_out / "stills"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        run_cmd([
            "node", str(RENDER_JS), str(shot_file),
            "--project", str(PROJECT),
            "--out", str(out_dir),
            "--size", size, "--fps", fps, "--no-voice",
            "--stills", stills,
        ])
        return

    layers = ["all"] if mode == "preview" and layer == "auto" else (["map", "overlay"] if layer == "auto" else [layer])
    for lyr in layers:
        out_dir = base_out if lyr == "all" else (base_out / lyr)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        run_cmd([
            "node", str(RENDER_JS), str(shot_file),
            "--project", str(PROJECT),
            "--out", str(out_dir),
            "--size", size, "--fps", fps, "--no-voice",
            "--layer", lyr,
        ])


def main() -> None:
    parser = argparse.ArgumentParser(description="Render clips for plateau-award-2026")
    parser.add_argument("clip_ids", nargs="*", help="Clip IDs (e.g. S01 B01). Default: all clips in manifest.")
    parser.add_argument("--mode", choices=["preview", "final"], default="preview")
    parser.add_argument("--layer", choices=["auto", "all", "map", "overlay"], default="auto")
    parser.add_argument("--stills", help="Comma-separated seconds for still inspection")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    all_ids = [c["id"] for c in manifest["clips"]]
    targets = args.clip_ids or all_ids
    unknown = [cid for cid in targets if cid not in all_ids]
    if unknown:
        raise SystemExit(f"Unknown clip IDs: {unknown}")

    for cid in targets:
        print(f"\n=== Rendering {cid} ({args.mode}, layer={args.layer}) ===", flush=True)
        render_single(cid, args.mode, args.layer, args.stills)


if __name__ == "__main__":
    main()
