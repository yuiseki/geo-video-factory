"""python -m photos.photo_exif <photo>
What a photo's own binary says about where and how it was taken, and nothing made up: the size, the focal length in
pixels when the EXIF gives a 35 mm equivalent (by the diagonal, as the equivalent is defined), the GPS position and
how the phone found it, the compass direction when there is one, and from these how far to search around the position.

A focal length in millimetres without the sensor's size says nothing in pixels; then `fx` is None and the field of
view is to be searched (geo/photo_place.py --fov-range). A network or cell-tower position is tens to hundreds of
metres off, a satellite fix a few metres: the search radius follows GPSProcessingMethod."""
import json
import math
import sys

from PIL import Image

# network: three photos taken in a garden were 190, 310 and 360 m from where their network fix put them
SEARCH_RADIUS = {"GPS": 30.0, "FUSED": 50.0, "network": 500.0, "CELLID": 300.0, None: 80.0}
FULL_FRAME_DIAGONAL = math.hypot(36.0, 24.0)


def _degrees(value, ref):
    x = float(value[0]) + float(value[1]) / 60 + float(value[2]) / 3600
    return -x if ref in ("S", "W") else x


def camera_from_exif(path):
    with Image.open(path) as im:
        width, height = im.size
        exif = im.getexif()
        sub, gps = exif.get_ifd(0x8769), exif.get_ifd(0x8825)
    if not gps or not all(k in gps for k in (1, 2, 3, 4)):
        raise ValueError(f"no GPS position in the EXIF of {path}")
    method = gps.get(27)
    if isinstance(method, bytes):          # an EXIF "undefined" string: 8 bytes naming the character set, then the text
        method = (method[8:] if method[:5] in (b"ASCII", b"UNICO", b"JIS\0\0") else method).split(b"\0")[0]
        method = method.decode("ascii", "replace").strip() or None
    f35 = int(sub.get(0xA405) or 0)
    focal = float(sub.get(0x920A)) if sub.get(0x920A) else None
    if f35 > 0:
        fx = f35 * math.hypot(width, height) / FULL_FRAME_DIAGONAL
        fx_from = f"FocalLengthIn35mmFilm {f35} mm on the diagonal"
    else:
        fx, fx_from = None, f"no 35 mm equivalent (FocalLength {focal} mm, sensor size unknown): search the field of view"
    heading = float(gps[17]) if 17 in gps else None
    out = {"width": width, "height": height, "fx": fx, "fx_from": fx_from,
           "lat": _degrees(gps[2], gps[1]), "lon": _degrees(gps[4], gps[3]),
           "altitude": float(gps[6]) if 6 in gps else None, "gps_method": method, "heading": heading,
           "search_radius_m": SEARCH_RADIUS.get(method, SEARCH_RADIUS[None])}
    if fx is not None:
        out["hfov_deg"] = math.degrees(2 * math.atan(width / 2 / fx))
    return out


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    print(json.dumps(camera_from_exif(argv[0]), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
