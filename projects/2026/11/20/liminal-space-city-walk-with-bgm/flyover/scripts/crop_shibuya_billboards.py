#!/usr/bin/env python3
"""Crop and perspective-rectify real Shibuya Scramble Crossing billboards and neon signs
from the commercial-use Shibuya reference photos into flyover/assets/billboards/.
"""
from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np


def warp_quad(
    img: np.ndarray,
    src_pts: list[tuple[float, float]],
    out_w: int,
    out_h: int,
) -> np.ndarray:
    """Perspective-rectify a quadrilateral [TL, TR, BR, BL] into (out_w, out_h)."""
    src = np.array(src_pts, dtype=np.float32)
    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, M, (out_w, out_h), flags=cv2.INTER_LANCZOS4)


def main() -> None:
    flyover_dir = Path(__file__).resolve().parents[1]
    photos_dir = flyover_dir / "assets/photos/shibuya_crossing"
    out_dir = flyover_dir / "assets/billboards"
    out_dir.mkdir(parents=True, exist_ok=True)

    im_014 = cv2.imread(str(photos_dir / "014_Shibuya_Crossing_Kis-My-Ft2_album_billboard_2024.jpg"))
    im_010 = cv2.imread(str(photos_dir / "010_Shibuya_Crossing_Tokyo_13001951595.jpg"))
    im_022 = cv2.imread(str(photos_dir / "022_Shibuya_screens.jpg"))
    im_018 = cv2.imread(str(photos_dir / "018_Shibuya_crossing_2018_39527815350.jpg"))
    im_006 = cv2.imread(str(photos_dir / "006_Shibuya_2018_44468961270.jpg"))
    if im_014 is None or im_010 is None or im_022 is None or im_018 is None or im_006 is None:
        raise FileNotFoundError("Missing reference photos")

    # All coordinates in 1920x1440 pixels: [TL, TR, BR, BL]
    crops = [
        (
            "sign_salonpas.png",
            im_014,
            [(1326, 38), (1642, 42), (1640, 405), (1324, 408)],
            512,
            600,
        ),
        (
            "sign_rakuten.png",
            im_014,
            [(1315, 578), (1638, 576), (1636, 868), (1314, 865)],
            512,
            460,
        ),
        (
            "sign_dmmtv.png",
            im_014,
            [(1322, 924), (1614, 916), (1612, 1178), (1320, 1172)],
            512,
            440,
        ),
        (
            "sign_taiseido.png",
            im_014,
            [(1304, 1222), (1584, 1218), (1584, 1296), (1304, 1296)],
            512,
            144,
        ),
        (
            "sign_sansenri.png",
            im_014,
            [(1204, 575), (1276, 566), (1278, 814), (1206, 814)],
            192,
            640,
        ),
        (
            "sign_monja.png",
            im_014,
            [(1122, 425), (1194, 434), (1194, 678), (1122, 668)],
            192,
            640,
        ),
        (
            "sign_nishimura_top.png",
            im_014,
            [(730, 206), (1134, 270), (1134, 540), (730, 488)],
            768,
            512,
        ),
        (
            "sign_bigecho.png",
            im_014,
            [(1846, 474), (1896, 474), (1896, 756), (1846, 756)],
            128,
            720,
        ),
        (
            "sign_109mens.png",
            im_010,
            [(1662, 102), (1914, 86), (1914, 240), (1662, 248)],
            512,
            300,
        ),
        (
            "sign_qfront_screen.png",
            im_010,
            [(880, 332), (1062, 336), (1062, 474), (880, 472)],
            512,
            384,
        ),
        (
            "sign_seibu_top.png",
            im_010,
            [(1232, 355), (1362, 372), (1362, 405), (1232, 390)],
            512,
            140,
        ),
        (
            "sign_qfront_night_screen.png",
            im_022,
            [(416, 84), (524, 96), (524, 152), (416, 144)],
            768,
            512,
        ),
        (
            "sign_qfront_starbucks.png",
            im_022,
            [(406, 224), (554, 232), (554, 272), (406, 266)],
            768,
            220,
        ),
        (
            "sign_matsumoto.png",
            im_014,
            [(560, 680), (705, 680), (705, 990), (560, 990)],
            280,
            600,
        ),
        # High-res night crops from 018 (1920x1280) & 006 (1920x1440)
        (
            "sign_qfront_top_018.png",
            im_018,
            [(900, 128), (1192, 60), (1198, 178), (906, 250)],
            768,
            320,
        ),
        (
            "sign_qfront_mid_018.png",
            im_018,
            [(902, 360), (1202, 290), (1212, 472), (908, 520)],
            768,
            480,
        ),
        (
            "sign_qfront_lower_018.png",
            im_018,
            [(885, 628), (1358, 595), (1368, 905), (892, 912)],
            960,
            620,
        ),
        (
            "sign_qfront_logo_006.png",
            im_006,
            [(1158, 232), (1380, 200), (1380, 286), (1158, 314)],
            640,
            240,
        ),
        (
            "sign_uc_018.png",
            im_018,
            [(6, 256), (160, 290), (144, 442), (0, 412)],
            384,
            420,
        ),
        (
            "sign_nishimura_green_018.png",
            im_018,
            [(132, 560), (312, 514), (308, 604), (128, 642)],
            512,
            240,
        ),
        (
            "sign_f21_018.png",
            im_018,
            [(618, 475), (786, 480), (784, 592), (618, 586)],
            512,
            340,
        ),
        (
            "sign_seibu_vert_018.png",
            im_018,
            [(1516, 332), (1562, 355), (1592, 650), (1546, 638)],
            160,
            768,
        ),
    ]

    for fname, img, pts, w, h in crops:
        warped = warp_quad(img, pts, w, h)
        out_path = out_dir / fname
        cv2.imwrite(str(out_path), warped)
        print(f"Saved {out_path.name} ({w}x{h})")


if __name__ == "__main__":
    main()
