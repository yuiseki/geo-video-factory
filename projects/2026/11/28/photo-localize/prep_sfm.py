"""Photos from different cameras, ready for visloc-rs SfM with per-image intrinsics.

    python prep_sfm.py <list.txt> <out dir> [long side]

<list.txt> holds one photo path per line. Each photo is turned upright, scaled so its
longer side is <long side> (default 2048), and saved as <out dir>/images/NNN.jpg with
its EXIF (GPS included) and the orientation tag reset. <out dir>/calib/ gets a COLMAP
text model with one PINHOLE camera per photo, focal length from the EXIF 35 mm
equivalent over the frame diagonal, for --input-colmap-calibration. A photo without
GPS or a 35 mm focal length is skipped and named on stdout.
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageOps

DIAG_35MM = math.hypot(36, 24)


def main(listing, out, long_side=2048):
    out = Path(out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "calib").mkdir(exist_ok=True)
    cams, imgs, n = [], [], 0
    for src in Path(listing).read_text(encoding="utf-8").split("\n"):
        if not src:
            continue
        im = Image.open(src)
        ex = im.getexif()
        f35 = ex.get_ifd(0x8769).get(41989)
        if not f35 or not ex.get_ifd(0x8825).get(2):
            print("skipped", src)
            continue
        im = ImageOps.exif_transpose(im)
        s = long_side / max(im.size)
        im = im.convert("RGB").resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        ex = im.getexif()
        ex[0x0112] = 1
        n += 1
        name = f"{n:03d}.jpg"
        im.save(out / "images" / name, quality=95, exif=ex)
        f = f35 / DIAG_35MM * math.hypot(*im.size)
        cams.append(f"{n} PINHOLE {im.width} {im.height} {f:.2f} {f:.2f} {im.width / 2} {im.height / 2}")
        imgs.append(f"{n} 1 0 0 0 0 0 0 {n} {name}\n")
        print(name, src)
    (out / "calib" / "cameras.txt").write_text("\n".join(cams) + "\n", encoding="utf-8")
    (out / "calib" / "images.txt").write_text("\n".join(imgs) + "\n", encoding="utf-8")
    (out / "calib" / "points3D.txt").write_text("", encoding="utf-8")
    print(n, "photos ready")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(int(a) for a in sys.argv[3:4]))
