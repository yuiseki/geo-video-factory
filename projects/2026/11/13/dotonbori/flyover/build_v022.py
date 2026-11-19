#!/usr/bin/env python3
"""Generate v0.2.2 chapter specs using minami_fixed (corrected Namba station buildings)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    v022_dir = ROOT / "shots/v0.2.2"
    v022_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((ROOT / "chapters.v0.2.1.json").read_text(encoding="utf-8"))
    new_chapters = []
    for ch in manifest["chapters"]:
        ch_id = ch["id"]
        spec = json.loads((ROOT / ch["spec"]).read_text(encoding="utf-8"))
        for entry in spec.get("plateauBuildings", []):
            if entry.get("manifest") == "assets/city/minami/manifest.json":
                entry["manifest"] = "assets/city/minami_fixed/manifest.json"
        spec_rel = f"shots/v0.2.2/{ch_id}.json"
        (ROOT / spec_rel).write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        new_chapters.append({"id": ch_id, "title": ch["title"], "spec": spec_rel})

    manifest["chapters"] = new_chapters
    (ROOT / "chapters.v0.2.2.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(new_chapters)} chapters in {v022_dir}")


if __name__ == "__main__":
    main()
