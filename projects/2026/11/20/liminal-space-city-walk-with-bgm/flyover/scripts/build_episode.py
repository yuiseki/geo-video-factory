#!/usr/bin/env python3
"""Build 3-chapter first-person Shibuya Backrooms x Vaporwave episode shots (total ~96s)."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_walk_shot import build_constant_speed_keys


def make_doc(shots: list[dict]) -> dict:
    return {
        "width": 1280,
        "height": 720,
        "fps": 24,
        "base": "seamlessphoto",
        "world": False,
        "dem": "gsi",
        "hillshade": False,
        "sky": {
            "sky-color": "#060612",
            "horizon-color": "#26143d",
            "fog-color": "#1d1030",
            "sky-horizon-blend": 0.68,
            "horizon-fog-blend": 0.78,
            "fog-ground-blend": 0.55,
        },
        "credits": [
            "建物: 国土交通省 PLATEAU (渋谷区 2025)"
        ],
        "plateauBuildings": {
            "manifest": "assets/buildings-shibuya-upscaled/manifest.json",
            "heightOffset": -39,
            "workers": 3,
            "recolorFromOrtho": False,
            "night": [[0, 0.86]],
        },
        "shots": shots,
    }


def main() -> None:
    flyover_dir = Path(__file__).resolve().parents[1]
    shots_dir = flyover_dir / "shots/episode-v1.0.0"
    shots_dir.mkdir(parents=True, exist_ok=True)

    ground_overlay = {
        "type": "image",
        "src": "assets/ground/shibuya_crossing_procedural_4x.png",
        "bbox": [139.69749748706818, 35.659000466530415, 139.7011023759842, 35.66100103417491],
    }

    speed_mps = 1.15

    # Chapter 1: Crossing Scramble Crossing toward Center-gai entrance (~37m, ~32s)
    ch1_wp = [
        {"center": [139.70048, 35.65955], "zoom": 21.45, "pitch": 85, "bearing": -45},
        {"center": [139.70020, 35.65978], "zoom": 21.55, "pitch": 85, "bearing": -45},
    ]
    d1, dur1, k1 = build_constant_speed_keys(ch1_wp, speed_mps=speed_mps)
    ch1 = make_doc([{"duration": dur1, "ease": "linear", "keys": k1, "overlays": [ground_overlay]}])
    (shots_dir / "ch01_crossing.json").write_text(json.dumps(ch1, ensure_ascii=False, indent=2), encoding="utf-8")

    # Chapter 2: Walking down Shibuya Center-gai past the curve (~37m, ~32s)
    ch2_wp = [
        {"center": [139.69968, 35.66009], "zoom": 21.65, "pitch": 85, "bearing": -70},
        {"center": [139.69930, 35.66018], "zoom": 21.65, "pitch": 85, "bearing": -68},
    ]
    d2, dur2, k2 = build_constant_speed_keys(ch2_wp, speed_mps=speed_mps)
    ch2 = make_doc([{"duration": dur2, "ease": "linear", "keys": k2, "overlays": [ground_overlay]}])
    (shots_dir / "ch02_centergai_mid.json").write_text(json.dumps(ch2, ensure_ascii=False, indent=2), encoding="utf-8")

    # Chapter 3: Deep Center-gai wandering with gentle left-right glance (~37m, ~32s)
    ch3_wp = [
        {"center": [139.69878, 35.66034], "zoom": 21.65, "pitch": 85, "bearing": -67},
        {"center": [139.69862, 35.66040], "zoom": 21.65, "pitch": 85, "bearing": -60},
        {"center": [139.69848, 35.66045], "zoom": 21.65, "pitch": 85, "bearing": -73},
        {"center": [139.69838, 35.66049], "zoom": 21.65, "pitch": 85, "bearing": -66},
    ]
    d3, dur3, k3 = build_constant_speed_keys(ch3_wp, speed_mps=speed_mps)
    ch3 = make_doc([{"duration": dur3, "ease": "linear", "keys": k3, "overlays": [ground_overlay]}])
    (shots_dir / "ch03_centergai_deep.json").write_text(json.dumps(ch3, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"ch01: {d1:.1f}m / {dur1:.1f}s")
    print(f"ch02: {d2:.1f}m / {dur2:.1f}s")
    print(f"ch03: {d3:.1f}m / {dur3:.1f}s")


if __name__ == "__main__":
    main()
