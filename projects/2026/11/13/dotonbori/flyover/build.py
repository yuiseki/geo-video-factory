#!/usr/bin/env python3
"""Generate v0.2.1 chapter specs with Dotonbori river-skimming and Cosmosquare orbit shots."""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def apply_ch01_river_skim(ch1: dict) -> None:
    shots = ch1["shots"]
    # 14..16: West -> East along Dotonbori River centerline
    pts_w2e = [
        ([135.4978, 34.66900], 17.7, 75, 89),
        ([135.5004, 34.66904], 18.0, 77, 89),
        ([135.5030, 34.66906], 18.2, 77, 89),
        ([135.5055, 34.66904], 17.8, 75, 89),
    ]
    for offset, idx in enumerate((14, 15, 16)):
        c0, z0, p0, b0 = pts_w2e[offset]
        c1, z1, p1, b1 = pts_w2e[offset + 1]
        shots[idx]["from"] = {"center": c0, "zoom": z0, "pitch": p0, "bearing": b0}
        shots[idx]["to"] = {"center": c1, "zoom": z1, "pitch": p1, "bearing": b1}
        shots[idx]["ease"] = "linear"

    # 22..23: East -> West ultra-low skim over Dotonbori River
    pts_e2w_a = [
        ([135.5055, 34.66904], 17.9, 76, -90),
        ([135.5034, 34.66906], 18.2, 78, -90),
        ([135.5012, 34.66905], 18.2, 78, -90),
    ]
    for offset, idx in enumerate((22, 23)):
        c0, z0, p0, b0 = pts_e2w_a[offset]
        c1, z1, p1, b1 = pts_e2w_a[offset + 1]
        shots[idx]["from"] = {"center": c0, "zoom": z0, "pitch": p0, "bearing": b0}
        shots[idx]["to"] = {"center": c1, "zoom": z1, "pitch": p1, "bearing": b1}
        shots[idx]["ease"] = "linear"

    # 26..28: Continue East -> West from Ebisubashi toward Fukari-bashi
    pts_e2w_b = [
        ([135.5016, 34.66905], 18.0, 76, -90),
        ([135.5003, 34.66903], 18.1, 77, -90),
        ([135.4990, 34.66901], 17.8, 75, -90),
        ([135.4978, 34.66900], 17.4, 72, -90),
    ]
    for offset, idx in enumerate((26, 27, 28)):
        c0, z0, p0, b0 = pts_e2w_b[offset]
        c1, z1, p1, b1 = pts_e2w_b[offset + 1]
        shots[idx]["from"] = {"center": c0, "zoom": z0, "pitch": p0, "bearing": b0}
        shots[idx]["to"] = {"center": c1, "zoom": z1, "pitch": p1, "bearing": b1}
        shots[idx]["ease"] = "linear"


def apply_cosmosquare_orbit(spec: dict, indices: list[int], center: list[float], zoom: float, pitch: float, b_start: float, b_end: float) -> None:
    shots = spec["shots"]
    n = len(indices)
    for k, idx in enumerate(indices):
        b0 = round(lerp(b_start, b_end, k / n), 2)
        b1 = round(lerp(b_start, b_end, (k + 1) / n), 2)
        shots[idx]["from"] = {"center": list(center), "zoom": zoom, "pitch": pitch, "bearing": b0}
        shots[idx]["to"] = {"center": list(center), "zoom": zoom, "pitch": pitch, "bearing": b1}
        shots[idx]["ease"] = "linear"


def main() -> None:
    v020_dir = ROOT / "shots/v0.2.0"
    v021_dir = ROOT / "shots/v0.2.1"
    v021_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((ROOT / "chapters.v0.2.0.json").read_text(encoding="utf-8"))
    new_chapters = []
    for ch in manifest["chapters"]:
        ch_id = ch["id"]
        spec = json.loads((ROOT / ch["spec"]).read_text(encoding="utf-8"))
        if ch_id == "ch01":
            apply_ch01_river_skim(spec)
        elif ch_id == "ch05":
            apply_cosmosquare_orbit(
                spec,
                list(range(14, 21)),
                center=[135.4125, 34.6427],
                zoom=15.8,
                pitch=58,
                b_start=-90,
                b_end=90,
            )
        elif ch_id == "ch06":
            apply_cosmosquare_orbit(
                spec,
                list(range(19, 27)),
                center=[135.4125, 34.6410],
                zoom=15.8,
                pitch=60,
                b_start=0,
                b_end=360,
            )
        spec_rel = f"shots/v0.2.1/{ch_id}.json"
        (ROOT / spec_rel).write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        new_chapters.append({"id": ch_id, "title": ch["title"], "spec": spec_rel})

    manifest["chapters"] = new_chapters
    (ROOT / "chapters.v0.2.1.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(new_chapters)} chapters in {v021_dir}")


if __name__ == "__main__":
    main()
