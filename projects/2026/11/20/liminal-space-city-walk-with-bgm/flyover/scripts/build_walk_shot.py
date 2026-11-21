#!/usr/bin/env python3
"""Build first-person walking shot JSONs with constant human walking speed."""
from __future__ import annotations

import json
import math
from pathlib import Path


def haversine_m(p1: list[float], p2: list[float]) -> float:
    r = 6371000.0
    lon1, lat1 = map(math.radians, p1)
    lon2, lat2 = map(math.radians, p2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2.0 * r * math.asin(math.sqrt(a))


def interpolate_point(p1: list[float], p2: list[float], ratio: float) -> list[float]:
    return [
        round(p1[0] + (p2[0] - p1[0]) * ratio, 6),
        round(p1[1] + (p2[1] - p1[1]) * ratio, 6),
    ]


def build_constant_speed_keys(
    waypoints: list[dict], speed_mps: float = 1.15
) -> tuple[float, float, list[dict]]:
    cum = [0.0]
    for i in range(len(waypoints) - 1):
        cum.append(cum[-1] + haversine_m(waypoints[i]["center"], waypoints[i + 1]["center"]))
    total_dist = cum[-1]
    duration = round(total_dist / speed_mps, 2)
    keys = []
    for wp, dist in zip(waypoints, cum):
        t = round(dist / total_dist, 4) if total_dist > 0 else 0.0
        keys.append(
            {
                "t": t,
                "center": wp["center"],
                "zoom": wp["zoom"],
                "pitch": wp["pitch"],
                "bearing": wp["bearing"],
            }
        )
    return total_dist, duration, keys


def base_doc(shots: list[dict]) -> dict:
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
        "credits": ["建物: 国土交通省 PLATEAU (渋谷区 2025)"],
        "plateauBuildings": {
            "manifest": "assets/buildings-shibuya/manifest.json",
            "heightOffset": -39,
            "workers": 3,
            "recolorFromOrtho": False,
            "night": [[0, 0.86]],
        },
        "shots": shots,
    }


def main() -> None:
    shots_dir = Path(__file__).resolve().parents[1] / "shots"
    speed_mps = 1.15  # ~4.1 km/h calm late-night human walking pace

    # 1. 24s realistic human walk: Scramble Crossing -> Center-gai entrance (~27.6m)
    p_start = [139.70042, 35.65960]
    p_end = [139.70019, 35.65978]
    dist_short = haversine_m(p_start, p_end)
    # Adjust p_start slightly if needed so distance is ~27.6m (24s at 1.15 m/s)
    short_waypoints = [
        {"center": [139.70042, 35.65960], "zoom": 21.45, "pitch": 85, "bearing": -45},
        {"center": [139.70020, 35.65978], "zoom": 21.55, "pitch": 85, "bearing": -45},
    ]
    d1, dur1, k1 = build_constant_speed_keys(short_waypoints, speed_mps=speed_mps)
    short_path = shots_dir / "shibuya-walk-crossing-v7.json"
    short_path.write_text(
        json.dumps(base_doc([{"duration": dur1, "ease": "linear", "keys": k1}]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {short_path.name}: dist={d1:.1f}m, duration={dur1:.1f}s ({speed_mps} m/s)")

    # 2. Full course (~293m, ~255s / 4m15s) at 1.15 m/s
    full_waypoints = [
        {"center": [139.70055, 35.65948], "zoom": 21.4, "pitch": 85, "bearing": -45},
        {"center": [139.70022, 35.65976], "zoom": 21.5, "pitch": 85, "bearing": -45},
        {"center": [139.69993, 35.65999], "zoom": 21.6, "pitch": 85, "bearing": -46},
        {"center": [139.69968, 35.66009], "zoom": 21.6, "pitch": 85, "bearing": -68},
        {"center": [139.69881, 35.66033], "zoom": 21.5, "pitch": 85, "bearing": -67},
        {"center": [139.69775, 35.66072], "zoom": 21.5, "pitch": 85, "bearing": -66},
    ]
    d2, dur2, k2 = build_constant_speed_keys(full_waypoints, speed_mps=speed_mps)
    full_path = shots_dir / "shibuya-walk-full-v7.json"
    full_path.write_text(
        json.dumps(base_doc([{"duration": dur2, "ease": "linear", "keys": k2}]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {full_path.name}: dist={d2:.1f}m, duration={dur2:.1f}s ({speed_mps} m/s)")


if __name__ == "__main__":
    main()
