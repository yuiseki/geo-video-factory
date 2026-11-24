"""geometry_map.py <tris.npz> <work_dir> <name=osm_way_id>...
The prior of the world model: which PLATEAU triangles belong to each named building.
Footprints come from OpenStreetMap ways (read once from OVERPASS_URL and cached in <work_dir>), triangles
are assigned by their centroid, and the result is drawn from above so that the assignment can be checked
by eye. Writes <work_dir>/buildings.npz (one triangle array per name), footprints.json and geometry_map.png."""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "packages" / "pipeline"))
from buildings import glb_spatial as gs  # noqa: E402
from buildings.plateau_mesh import enu_frame  # noqa: E402

OVERPASS = os.environ.get("OVERPASS_URL", "https://overpass.yuiseki.net/api/interpreter")


def to_enu(lonlat, origin):
    o, m = enu_frame(*origin)
    return np.array([(m @ (np.array(gs._ecef(lo, la, 0)) - o))[:2] for lo, la in lonlat])


def inside(points, polygon, margin):
    from matplotlib.path import Path as MplPath
    area = 0.5 * np.sum(polygon[:-1, 0] * polygon[1:, 1] - polygon[1:, 0] * polygon[:-1, 1])
    return MplPath(polygon).contains_points(points, radius=margin * (1 if area > 0 else -1))


def facades(tris, step=15.0):
    """Wall area (m2) per outward azimuth bin: where the building has faces worth texturing."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    area = 0.5 * np.linalg.norm(n, axis=1)
    wall = (area > 1e-6) & (np.abs(n[:, 2]) < 0.3 * 2 * area)
    az = (np.degrees(np.arctan2(n[wall, 0], n[wall, 1])) + 360) % 360
    hist = np.zeros(int(360 / step))
    np.add.at(hist, (az / step).astype(int) % len(hist), area[wall])
    return {int(i * step): round(float(a)) for i, a in enumerate(hist) if a > 0.03 * hist.sum()}


def main(argv):
    tris_path, work = argv[0], Path(argv[1])
    names = dict(a.split("=") for a in argv[2:])
    work.mkdir(parents=True, exist_ok=True)
    z = np.load(tris_path)
    tris, origin = z["tris"], z["origin"]
    cache = work / "osm_ways.json"
    if not cache.exists():
        q = "[out:json][timeout:40];way(id:%s);out tags geom;" % ",".join(names.values())
        req = urllib.request.Request(OVERPASS, urllib.parse.urlencode({"data": q}).encode(),
                                     {"User-Agent": "geo-video-factory world_model"})
        cache.write_bytes(urllib.request.urlopen(req, timeout=50).read())
    ways = {str(e["id"]): e for e in json.loads(cache.read_text())["elements"]}
    cen = tris.mean(axis=1)
    out, foot, report = {}, {}, {}
    for name, wid in names.items():
        poly = to_enu([(p["lon"], p["lat"]) for p in ways[wid]["geometry"]], origin)
        pick = inside(cen[:, :2], poly, 1.5)
        t = tris[pick]
        out[name], foot[name] = t, poly.round(2).tolist()
        report[name] = {"osm": ways[wid]["tags"].get("name"), "triangles": int(pick.sum()),
                        "z": [round(float(t[..., 2].min()), 1), round(float(t[..., 2].max()), 1)],
                        "wall_m2_by_azimuth": facades(t)}
    np.savez_compressed(work / "buildings.npz", origin=origin, **out)
    (work / "footprints.json").write_text(json.dumps({"origin": origin.tolist(), "footprints": foot, "report": report},
                                                     ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    fig, ax = plt.subplots(figsize=(12, 12), dpi=110)
    near = (np.abs(cen[:, 0]) < 260) & (np.abs(cen[:, 1]) < 260)
    ax.add_collection(PolyCollection(tris[near][:, :, :2], facecolors="#d9d9d9", edgecolors="#9a9a9a", linewidths=0.15))
    for (name, t), c in zip(out.items(), ["#d1495b", "#00798c", "#edae49", "#66a182"]):
        ax.add_collection(PolyCollection(t[:, :, :2], facecolors=c, edgecolors="none", alpha=0.75))
        p = np.array(foot[name])
        ax.plot(p[:, 0], p[:, 1], color="black", lw=1.5)
        ax.annotate(f"{name}\n{report[name]['z'][1] - report[name]['z'][0]:.0f} m", p.mean(axis=0), ha="center",
                    fontsize=13, weight="bold")
    ax.set_xlim(-260, 160), ax.set_ylim(-160, 200), ax.set_aspect("equal"), ax.grid(alpha=0.3)
    ax.set_xlabel("east (m)"), ax.set_ylabel("north (m)")
    ax.set_title("PLATEAU LOD2 triangles assigned to each building (outline: OpenStreetMap)", fontsize=14)
    fig.savefig(work / "geometry_map.png", bbox_inches="tight")


if __name__ == "__main__":
    main(sys.argv[1:])
