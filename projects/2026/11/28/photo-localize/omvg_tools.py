"""openMVG on the same terms as the other SfM tools: focal lengths from the EXIF 35 mm equivalent in, an ENU model out.

    python omvg_tools.py focals <sfm_data.json> <image dir>        every view's own intrinsic gets f35 / 43.27 mm * diag
    python omvg_tools.py enu <COLMAP text model in ECEF> <out dir>  the same cameras in metres east, north, up

openMVG's sensor database has no recent phones, so the listing runs with a placeholder focal length and one
intrinsic per view (-g 0), and focals sets each from its photo. With GPS priors (-P, -m 0) openMVG works in
Earth-centred coordinates; enu moves a model exported by openMVG2Colmap into a local frame around the cameras'
mean and writes enu_origin.txt, so sfm_compare.py reads it like the others.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

A, F = 6378137.0, 1 / 298.257223563
E2 = F * (2 - F)
DIAG_35MM = math.hypot(36, 24)


def lla_to_ecef(lon, lat, alt):
    lo, la = math.radians(lon), math.radians(lat)
    n = A / math.sqrt(1 - E2 * math.sin(la) ** 2)
    return np.array([(n + alt) * math.cos(la) * math.cos(lo), (n + alt) * math.cos(la) * math.sin(lo),
                     (n * (1 - E2) + alt) * math.sin(la)])


def ecef_to_lla(x, y, z):
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - E2))
    for _ in range(10):
        n = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
        alt = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - E2 * n / (n + alt)))
    n = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
    return math.degrees(lon), math.degrees(lat), p / math.cos(lat) - n


def ecef_to_enu_rotation(lon, lat):
    lo, la = math.radians(lon), math.radians(lat)
    return np.array([[-math.sin(lo), math.cos(lo), 0],
                     [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)],
                     [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)]])


def ecef_model_to_enu(model, out):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import colmap_sfm as cs
    cams = cs.read_model(model)
    mean = np.mean([c for _, c in cams.values()], axis=0)
    lon0, lat0, _ = ecef_to_lla(*mean)
    m = ecef_to_enu_rotation(lon0, lat0)
    x0 = lla_to_ecef(lon0, lat0, 0.0)
    enu = {}
    for k, (r, c) in cams.items():
        lon, lat, _ = ecef_to_lla(*c)                     # exact place, then the sphere metres the readers use
        e, n = cs.sphere_enu(lon, lat, (lon0, lat0))
        enu[k] = {"R": r @ m.T, "C": np.array([e, n, (m @ (c - x0))[2]])}
    cs.write_model(Path(out) / "0", enu, (lon0, lat0))


def set_focals(data, f35):
    """data: openMVG sfm_data (JSON); f35: {filename: 35 mm equivalent focal length}."""
    intr = {i["key"]: i["value"]["ptr_wrapper"]["data"] for i in data["intrinsics"]}
    for v in data["views"]:
        d = v["value"]["ptr_wrapper"]["data"]
        f = f35.get(d["filename"])
        if f and d["id_intrinsic"] in intr:
            intr[d["id_intrinsic"]]["focal_length"] = f / DIAG_35MM * math.hypot(d["width"], d["height"])
    return data


def exif_f35(path):
    from PIL import Image
    v = Image.open(path).getexif().get_ifd(0x8769).get(41989)
    return float(v) if v else None


def main(argv):
    if argv[0] == "focals":
        p, img = Path(argv[1]), Path(argv[2])
        data = json.loads(p.read_text())
        f35 = {q.name: exif_f35(q) for q in img.glob("*.jpg")}
        p.write_text(json.dumps(set_focals(data, f35), indent=1))
        print(sum(1 for v in f35.values() if v), "focal lengths set")
    elif argv[0] == "enu":
        ecef_model_to_enu(Path(argv[1]), Path(argv[2]))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
