"""Whether OSM's marked crosswalks tell where a Shibuya street photo was taken: the painted bands against the asphalt.

    OVERPASS_URL=<your Overpass> python projects/2026/11/26/plateau-pp-ultra-after/crosswalk_eval.py

The same 31 SfM-aligned street photos as placement_eval.py, at their true heading, pitch and roll. Every OSM crosswalk
within 40 m becomes its painted band (the walking line, the crossing's width); the score of a standing point is the
mean brightness of the picture on the bands minus beside them (a band's width + 1.5 m along the road), in standard
deviations of the picture. The ground is 1.5 m below the true eye (the SfM frame's street is not at placement_eval's
GROUND everywhere). Every point within 10 m of the truth on a 0.5 m grid is scored: where the best one is, and how
many points score above the truth. The single bars are not used: their phase (bar or gap) is finer than OSM's lines.
Run from the repository root with packages/pipeline's Python, under the host's resource limits.
"""
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "packages/pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import placement_eval as pe
from buildings import glb_spatial as gs
from buildings.plateau_mesh import enu_frame
from buildings.blender_geo import crosswalk_stripes
from world_model.osm_crosswalks import crosswalks_file
from photos import photo_store

ORIGIN = (139.7005, 35.6595)
o, M = enu_frame(*ORIGIN)
def enu(lon, lat):
    return M @ (np.array(gs._ecef(lon, lat, 0)) - o)
bbox = [139.6965, 35.6563, 139.7045, 35.6627]
cw = json.loads(crosswalks_file(bbox).read_text())["crosswalks"]
rects, quads = [], []
for c in cw:
    a, b = enu(*c["line"][0])[:2], enu(*c["line"][-1])[:2]
    q = crosswalk_stripes(a, b, c["width"])
    quads.append(np.array(q))
print(len(cw), "crosswalks", sum(len(q) for q in quads), "bars", flush=True)
W = 480
GZ = [52.8]
def band(a, b, width, shift=0.0):
    a, b = np.asarray(a), np.asarray(b)
    u = (b - a) / np.linalg.norm(b - a); nn = np.array([-u[1], u[0]]); h = width / 2
    return np.array([a - nn * (h - shift), b - nn * (h - shift), b + nn * (h + shift), a + nn * (h + shift)])

BANDS = []
for c in cw:
    a, b = enu(*c["line"][0])[:2], enu(*c["line"][-1])[:2]
    if np.linalg.norm(b - a) < 2: continue
    BANDS.append((band(a, b, c["width"]), [band(a, b, c["width"], sh) for sh in (c["width"] + 1.5, -c["width"] - 1.5)]))

def score(gray, cam, s, eye):
    """mean brightness on the painted bands minus on the asphalt beside them (a band's width + 1.5 m along the road)."""
    R = np.asarray(cam["Rw"]); f, _, cx, cy = cam["params"]
    on = Image.new("L", gray.shape[::-1]); off = Image.new("L", gray.shape[::-1])
    don, doff = ImageDraw.Draw(on), ImageDraw.Draw(off)
    def draw(d, quad):
        c = (np.c_[quad, np.full(4, GZ[0])] - eye) @ R.T
        if (c[:, 2] < 1).any(): return False
        uv = c[:, :2] / c[:, 2:3] * f * s + np.array([cx * s, cy * s]); d.polygon([tuple(x) for x in uv], fill=1); return True
    for q, sides in BANDS:
        if np.hypot(*(q.mean(0) - eye[:2])) > 40: continue
        if draw(don, q):
            for sd in sides: draw(doff, sd)
    a = np.asarray(on, bool); b = np.asarray(off, bool) & ~a
    if a.sum() < 50 or b.sum() < 50: return np.nan
    return (gray[a].mean() - gray[b].mean()) / (gray.std() + 1e-9)

rows = []
for n, (key, cam) in enumerate(pe.street_cams()):
    with Image.open(photo_store.camera_photo(cam)) as im:
        s = W / im.width
        gray = np.asarray(im.convert("L").resize((W, round(im.height * s))), float)
    eye = np.asarray(cam["eye"], float); GZ[0] = eye[2] - 1.5
    offs = [(dx, dy) for dx in np.arange(-10, 10.5, 0.5) for dy in np.arange(-10, 10.5, 0.5)]
    sc = np.array([score(gray, cam, s, eye + np.array([dx, dy, 0])) for dx, dy in offs])
    t = sc[offs.index((0.0, 0.0))]
    ok = np.isfinite(sc)
    if not ok.any() or not np.isfinite(t):
        print(n, key[:40], "no bars in view", flush=True); rows.append(None); continue
    best = int(np.nanargmax(sc)); d = math.hypot(*offs[best])
    rank = int(np.sum(sc[ok] > t))
    print(n, key[:40], f"truth score {t:+.2f}  best {sc[best]:+.2f} at {d:.1f} m  truth rank {rank}/{ok.sum()}", flush=True)
    rows.append((t, d, rank, int(ok.sum())))
got = [r for r in rows if r]
print("photos with bars:", len(got), " best within 1 m:", sum(r[1] <= 1 for r in got),
      " truth score > 0:", sum(r[0] > 0 for r in got), " median rank", sorted(r[2] for r in got)[len(got)//2] if got else None)
