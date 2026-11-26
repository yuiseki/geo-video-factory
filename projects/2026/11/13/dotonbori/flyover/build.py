#!/usr/bin/env python3
"""Generate v0.2.0 chapter specs and manifest with PLATEAU 3D buildings and textures."""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BUILDINGS = {
    "minami": {"manifest": "assets/city/minami/manifest.json", "heightOffset": -38, "workers": 3},
    "cosmosquare": {"manifest": "assets/city/cosmosquare/manifest.json", "heightOffset": -38, "workers": 3},
    "asakusa-ryogoku": {"manifest": "assets/city/asakusa-ryogoku/manifest.json", "heightOffset": -39, "workers": 3},
    "shimbashi": {"manifest": "assets/city/shimbashi/manifest.json", "heightOffset": -39, "workers": 3},
}

CHAPTER_BUILDINGS = {
    1: ["minami"],
    2: ["asakusa-ryogoku"],
    3: ["asakusa-ryogoku"],
    4: ["shimbashi"],
    5: ["cosmosquare"],
    6: ["cosmosquare", "minami"],
    7: ["minami", "cosmosquare"],
    8: ["minami", "cosmosquare"],
}

EXTRA_CREDITS = [
    "3D都市モデル：国土交通省 PLATEAU（大阪市 2025・東京都 2025）",
    "建物外形補完・外観推定を含む",
]


def main() -> None:
    base_spec = json.loads((ROOT / "shots/dotonbori.v0.1.7.json").read_text(encoding="utf-8"))
    shots = base_spec["shots"]

    starts: list[tuple[int, str]] = []
    for idx, shot in enumerate(shots):
        for ov in shot.get("overlays", []):
            if ov.get("type") == "chapter":
                starts.append((idx, ov["text"]))
    starts.append((len(shots), "END"))

    out_dir = ROOT / "shots/v0.2.0"
    out_dir.mkdir(parents=True, exist_ok=True)

    base_credits = list(base_spec.get("credits", []))
    for credit in EXTRA_CREDITS:
        if credit not in base_credits:
            base_credits.append(credit)

    chapters_manifest = {
        "series": "YuisekinTV",
        "fps": base_spec.get("fps", 24),
        "size": f"{base_spec.get('width', 1920)}x{base_spec.get('height', 1080)}",
        "cardSeconds": 2.5,
        "chapters": [],
    }

    preview_shots = []
    preview_indices = {0, 42, 74, 105}

    for ch_idx in range(len(starts) - 1):
        ch_num = ch_idx + 1
        a, title = starts[ch_idx]
        b, _ = starts[ch_idx + 1]
        ch_id = f"ch{ch_num:02d}"
        ch_spec = {k: copy.deepcopy(v) for k, v in base_spec.items() if k != "shots"}
        ch_spec["hillshade"] = False
        ch_spec["credits"] = base_credits
        ch_spec["plateauBuildings"] = [BUILDINGS[name] for name in CHAPTER_BUILDINGS[ch_num]]
        ch_spec["shots"] = copy.deepcopy(shots[a:b])

        spec_rel = f"shots/v0.2.0/{ch_id}.json"
        (ROOT / spec_rel).write_text(json.dumps(ch_spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        chapters_manifest["chapters"].append({
            "id": ch_id,
            "title": title,
            "spec": spec_rel,
        })
        for idx in range(a, b):
            if idx in preview_indices:
                s = copy.deepcopy(shots[idx])
                s["duration"] = 1
                s.pop("lines", None)
                preview_shots.append(s)

    (ROOT / "chapters.v0.2.0.json").write_text(
        json.dumps(chapters_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    preview_spec = {k: copy.deepcopy(v) for k, v in base_spec.items() if k != "shots"}
    preview_spec["hillshade"] = False
    preview_spec["credits"] = base_credits
    preview_spec["plateauBuildings"] = [
        BUILDINGS["minami"],
        BUILDINGS["asakusa-ryogoku"],
        BUILDINGS["shimbashi"],
        BUILDINGS["cosmosquare"],
    ]
    preview_spec["shots"] = preview_shots
    (out_dir / "preview-buildings.json").write_text(
        json.dumps(preview_spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(chapters_manifest['chapters'])} chapters in {out_dir}")


if __name__ == "__main__":
    main()
