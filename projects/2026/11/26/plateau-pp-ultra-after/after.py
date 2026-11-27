"""Render the improved world model at the areas of plateau-pp-ultra-before, with the same views, into out/<name>/.

    OVERPASS_URL=<your Overpass> python projects/2026/11/26/plateau-pp-ultra-after/after.py [--spots] [name ...]

Run from the repository root with packages/pipeline's Python, under the host's resource limits; blender on PATH.
Same areas, scene and views as the before project (its render_area), with the improvements switched on:

    --baked-look   PLATEAU++ v0.1.0 as baked (window pattern x wall colour, roof photo), lit windows at night
    --atlas-fade   atlases as opaque as their texels were well seen (quality.png)
    --streets      aged asphalt and the zebra bars of OSM's marked crossings (world_model/osm_crosswalks.py)

The atlases are atlas_after.py's (the before project's placements without the photos that had no roofline; with
quality.png) when present, else the before project's; Shibuya's are rebuilt with quality.png by shibuya_atlases.sh
into work/shibuya/ and used from there when present. When work/spots/<spot>/<name>/ holds a world (atlas_before.py
with --root, --spot and --registration: one spot's CC0/PD photos placed by SfM with the help of CC BY / BY-SA
photos), --spots makes its atlases replace the area's (both are the group within the same radius, and would overlap).
Off by default: the SfM models are put on the city by anchors placed one by one on the skyline, which land 30 to
300 m from where the models' fit puts them (Kaminarimon, Akihabara, Ginza 4-chome), and the photos are painted on
the wrong buildings.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEFORE = HERE.parent / "plateau-pp-ultra-before"
spec = importlib.util.spec_from_file_location("before", BEFORE / "before.py")
before = importlib.util.module_from_spec(spec)
spec.loader.exec_module(before)
from world_model.osm_crosswalks import crosswalks_file  # noqa: E402  (packages/pipeline, put on the path by before.py)
from world_model.osm_street_lamps import lamps_file  # noqa: E402


def after_layers(area: dict, t: str, bbox: list[float]) -> tuple[list[str], list[str], list[str]]:
    _, atlases, grounds = before.before_layers(area, t, bbox)
    work = HERE / "work" / area["name"]                                  # atlas_after.py: without roofline-less photos
    spots = sorted((HERE / "work" / "spots").glob(f"*/{area['name']}/world")) if USE_SPOTS else []
    if spots:        # --spots: one spot's photos joined by SfM with registration-only photos replace the area's atlas
        work = spots[0].parent
    mine = work / f"atlas_{t}" / "model.obj"
    cams = work / "world" / "layers" / f"cams_{t}.json"
    if cams.exists() and not json.loads(cams.read_text()):      # every photo left out: no atlas, not the before one
        atlases = [a for a in atlases if f"/work/{area['name']}/atlas_{t}/" not in a]
    elif mine.exists():
        atlases = [str(mine) if f"/work/{area['name']}/atlas_{t}/" in a else a for a in atlases] or [str(mine)]
    if area.get("world_model"):
        rebuilt = [HERE / "work" / area["name"] / a.format(t=t) / "model.obj" for a in before.ATLASES]
        if all(p.exists() for p in rebuilt):
            atlases = [str(p) for p in rebuilt] + [a for a in atlases if "/work/" + area["name"] + "/atlas_" in a]
    extra = ["--baked-look", "--atlas-fade", f"--streets={crosswalks_file(bbox)}",
             f"--lamps={lamps_file(bbox)}"] + (["--windows=1"] if t == "night" else [])
    return extra, atlases, grounds


USE_SPOTS = "--spots" in sys.argv[1:]


def main() -> None:
    conf = json.loads((BEFORE / "areas.json").read_text(encoding="utf-8"))
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    for area in conf["areas"]:
        if not names or area["name"] in names:
            before.render_area(area, conf["radius_m"], HERE / "out" / area["name"], layers=after_layers,
                               views=BEFORE / "render_views.py")


if __name__ == "__main__":
    main()
