"""Render the world model as it is today at every area of areas.json, day and night, into out/<name>/.

    OVERPASS_URL=<your Overpass> python projects/2026/11/26/plateau-pp-ultra-before/before.py [name ...]

Run from the repository root with packages/pipeline's Python, under the host's resource limits; blender on PATH.
Per area: PLATEAU++ v0.1.0 from the versioned shared cache (plateau_pp.cached), the ground height (ground_of), a scene with world_model/pp_scene.py (Shibuya also gets
the CC0 world model's photo atlases and ground; other areas their atlas_before.py atlas when it exists), then three
views (render_views.py). Nothing here is improved: this
is the baseline the plateau-pp-ultra-after project compares against. out/ is rebuilt every run.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "packages" / "pipeline"))
from buildings.gsi_footprints import dem_sampler  # noqa: E402
from buildings.plateau_pp import cached  # noqa: E402
from shared_cache import gsi_dir  # noqa: E402

GEOID_M = 36.7
ATLASES = ("around_{t}_cc0_v1b", "ekimae_{t}_cc0_v1", "magnet_{t}_cc0_v1", "qfront_{t}_cc0_v1", "s109_{t}_cc0_v1")
NIGHT = ["--dim=0.16", "--sky=0.015,0.02,0.045", "--sun=0.25"]     # pp_scene's night, as the Shibuya night layer used


def ground_of(area: dict, bbox: list[float]) -> float:
    """The ground on the ellipsoid at the centre: from the PLATEAU++ mesh when atlas_before.py made one (2nd percentile
    of the heights within 150 m), else areas.json's ground_z, else the GSI DEM (zoom 14, 10 m: off by 3 to 5 m where
    the centre falls on a slope, as at Shibuya and Ueno) + GEOID_M."""
    tris = HERE / "work" / area["name"] / "tris.npz"
    if tris.exists():
        import numpy as np
        t = np.load(tris)["tris"]
        near = np.linalg.norm(t.mean(axis=1)[:, :2], axis=1) < 150
        return float(np.percentile(t[near][:, :, 2], 2))
    if "ground_z" in area:
        return float(area["ground_z"])
    return dem_sampler(bbox, gsi_dir())(*area["center"]) + GEOID_M


def bbox_of(area: dict, r: float) -> list[float]:
    lon, lat = area["center"]
    dlon, dlat = r / (111320 * 0.8147), r / 110950
    return [round(lon - dlon, 6), round(lat - dlat, 6), round(lon + dlon, 6), round(lat + dlat, 6)]


def before_layers(area: dict, t: str, bbox: list[float]) -> tuple[list[str], list[str], list[str]]:
    """(extra pp_scene options, photo atlases, ground models) of the world model as it is today."""
    atlases, grounds = [], []
    own = HERE / "work" / area["name"] / f"atlas_{t}" / "model.obj"     # atlas_before.py's atlas of this area
    if own.exists():
        atlases.append(str(own))
    if area.get("world_model"):
        wm = REPO / area["world_model"]
        atlases += [str(wm / a.format(t=t) / "model.obj") for a in ATLASES]
        grounds.append(str(wm / f"ground_above_{t}_cc0_v1" / "model.obj"))
    return [], atlases, grounds


VIEWS = ("aerial", "roof", "street")


def render_area(area: dict, r: float, out: Path, layers=before_layers, views=HERE / "render_views.py") -> None:
    """One area's scene, day and night, and its views into out/ (rebuilt): what layers() says goes on PLATEAU++."""
    lon, lat = area["center"]
    bbox = bbox_of(area, r)
    pp = cached(bbox)
    ground = ground_of(area, bbox)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    info = {"area": area, "bbox": bbox, "plateau_pp": str(pp.relative_to(REPO)), "ground_z": round(ground, 2)}
    (out / "scene.json").write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"== {area['name']}: ground {ground:.1f} m, PLATEAU++ {pp.name}", flush=True)
    for t in ("day", "night"):
        extra, atlases, grounds = layers(area, t, bbox)
        args = [str(out / f"{t}.blend"), str(pp / "manifest.json"), f"--origin={lon},{lat}", "--centre=0,0",
                f"--radius={r + 150}", f"--ground-z={ground:.2f}"] + (NIGHT if t == "night" else []) + extra
        if atlases:
            args.append("--atlas=" + ",".join(atlases))
        if grounds:
            args.append("--ground=" + ",".join(grounds))
        subprocess.run(["blender", "-b", "--factory-startup", "-P",
                        str(REPO / "packages/pipeline/world_model/pp_scene.py"), "--", *args],
                       check=True, stdout=open(out / f"{t}_scene.log", "w"), stderr=subprocess.STDOUT)
        with open(out / f"{t}_render.log", "w") as log:
            for view in VIEWS:       # one Blender per view: EEVEE in one session sometimes drew the previous camera
                subprocess.run(["blender", "-b", str(out / f"{t}.blend"), "-P", str(views), "--",
                                str(out / "scene.json"), str(out), t, view],
                               check=True, stdout=log, stderr=subprocess.STDOUT)
        print(f"   {t}: rendered", flush=True)


def main() -> None:
    conf = json.loads((HERE / "areas.json").read_text(encoding="utf-8"))
    names = sys.argv[1:]
    for area in conf["areas"]:
        if not names or area["name"] in names:
            render_area(area, conf["radius_m"], HERE / "out" / area["name"])


if __name__ == "__main__":
    main()
