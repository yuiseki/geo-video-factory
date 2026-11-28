"""A photo_solve work directory whose place step is already done, from a camera another tool gave (MapAnything).

    python seed_place.py <cameras.json> <photo name> <photo file> <work dir> <ground z>

<cameras.json> is what mapanything_anchor.py writes (cameras in metres east, north, up from its "origin").
geo.photo_solve keeps its place step's answer in <work>/place/result.json and place/cams.json and reads them
instead of searching when they exist; this writes both, so photo_solve goes straight to the target building, SAM's
masks and the silhouette fit. The camera is moved to the photo's own origin (its EXIF position, as photo_solve's
step_exif reads it), its intrinsics are scaled from the model's working size to the photo's, and the eye is put at
<ground z> + 1.6 m, where photo_solve's silhouette fit holds it.
"""
import json
import math
import sys
from pathlib import Path

EYE_HEIGHT = 1.6


def shift(origin_from, origin_to):
    """Metres east and north from origin_to to origin_from: add it to move a point between the two frames."""
    kx = 111320 * math.cos(math.radians(origin_to[1]))
    return [(origin_from[0] - origin_to[0]) * kx, (origin_from[1] - origin_to[1]) * 110950]


def seeded(cam, origin_from, origin_to, width, height, ground):
    dx, dy = shift(origin_from, origin_to)
    s = width / cam["width"]
    eye = [cam["eye"][0] + dx, cam["eye"][1] + dy, ground + EYE_HEIGHT]
    fx, fy, cx, cy = cam["params"]
    return {"eye": eye, "Rw": cam["Rw"], "width": width, "height": height, "model": "PINHOLE",
            "params": [fx * s, fy * s, width / 2, height / 2]}


def heading_pitch_roll(Rw):
    r = [list(map(float, row)) for row in Rw]
    f, d = r[2], r[1]                     # forward and down in world coordinates
    heading = math.degrees(math.atan2(f[0], f[1])) % 360
    pitch = math.degrees(math.asin(max(-1, min(1, f[2]))))
    roll = math.degrees(math.atan2(-r[0][2], -d[2]))
    return heading, pitch, roll


def main(argv):
    cams, name, photo, work, ground = json.load(open(argv[0])), argv[1], Path(argv[2]), Path(argv[3]), float(argv[4])
    from PIL import Image, ImageOps
    sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "packages" / "pipeline"))
    from geo.photo_solve import step_exif
    work.mkdir(parents=True, exist_ok=True)
    ex = step_exif(photo, work)
    w, h = ImageOps.exif_transpose(Image.open(photo)).size
    cam = seeded(cams[name], cams["origin"], (ex["lon"], ex["lat"]), w, h, ground)
    hd, pt, rl = heading_pitch_roll(cam["Rw"])
    hfov = math.degrees(2 * math.atan(w / 2 / cam["params"][0]))
    best = {"east": cam["eye"][0], "north": cam["eye"][1], "up": cam["eye"][2], "heading": hd, "pitch": pt,
            "roll": rl, "hfov": hfov, "cost": None}
    (work / "place").mkdir(exist_ok=True)
    json.dump({"photo": photo.name, "ground": ground, "eye_height": EYE_HEIGHT, "best": best, "alone": True,
               "moved_m": math.hypot(*cam["eye"][:2]), "seeded": "mapanything"},
              open(work / "place" / "result.json", "w"), indent=1)
    json.dump({"seed": dict(cam, name=photo.name, photo=str(photo))}, open(work / "place" / "cams.json", "w"), indent=1)
    print(name, "seeded at", [round(v, 1) for v in cam["eye"]], "heading", round(hd, 1), "pitch", round(pt, 1))


if __name__ == "__main__":
    main(sys.argv[1:])
