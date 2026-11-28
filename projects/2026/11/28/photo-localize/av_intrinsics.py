"""AliceVision's cameraInit.sfm with every camera's focal length from the EXIF 35 mm equivalent.

    python av_intrinsics.py <cameraInit.sfm>      (rewritten in place)

cameraInit takes the sensor width from its database by phone model, which holds the main camera's: a phone's
ultra-wide or tele photo (another focal length in mm on a smaller sensor) gets a wrong field of view. Here each
group of views that share a 35 mm equivalent focal length gets its own intrinsic, with the sensor size that turns
the EXIF focal length in mm into f_px = f35 / 43.27 mm * the image diagonal, the same rule as prep_sfm.py.
"""
import copy
import json
import math
import sys
import zlib

DIAG_35MM = math.hypot(36, 24)


def fix(d):
    base = {i["intrinsicId"]: i for i in d["intrinsics"]}
    made = {}
    for v in d["views"]:
        md = v.get("metadata", {})
        f35, fmm = md.get("Exif:FocalLengthIn35mmFilm"), md.get("Exif:FocalLength")
        if not f35 or not fmm:
            continue
        key = (v["intrinsicId"], f35)
        if key not in made:
            i = copy.deepcopy(base[v["intrinsicId"]])
            w, h = float(v["width"]), float(v["height"])
            f_px = float(f35) / DIAG_35MM * math.hypot(w, h)
            sw = float(fmm) * w / f_px
            i.update(intrinsicId=str(zlib.crc32("/".join(key).encode()) % 2_000_000_000), sensorWidth=repr(sw), sensorHeight=repr(sw * h / w),
                     focalLength=fmm, initialFocalLength=fmm)
            made[key] = i
        v["intrinsicId"] = made[key]["intrinsicId"]
    used = {v["intrinsicId"] for v in d["views"]}
    d["intrinsics"] = [i for i in list(base.values()) + list(made.values()) if i["intrinsicId"] in used]
    return d


if __name__ == "__main__":
    p = sys.argv[1]
    d = fix(json.load(open(p)))
    json.dump(d, open(p, "w"), indent=2)
    print(len(d["intrinsics"]), "intrinsics")
