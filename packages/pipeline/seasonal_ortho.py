"""Seasonal color-transfer pipeline: Sentinel-2 L2A STAC/COG + GSI ortho + vegetation mask."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import gaussian_filter, map_coordinates

from cog_tiff import _read_u32_array, decode_deflate_rgb_tile, parse_tiff_ifd

STAC_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
USER_AGENT = "geo-video-factory/1.0"
GSI_SEAMLESSPHOTO_URL = "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg"


def _urlopen_retry(req: urllib.request.Request, retries: int = 3) -> bytes:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as exc:
            last_err = exc
            if attempt + 1 < retries:
                time.sleep(0.4 * (attempt + 1))
    assert last_err is not None
    raise last_err


def _http_range(url: str, start: int, end_inclusive: int) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"Range": f"bytes={start}-{end_inclusive}", "User-Agent": USER_AGENT},
    )
    return _urlopen_retry(req)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert uint8 sRGB image (H, W, 3) to float32 CIE L*a*b* (D65)."""
    srgb = np.asarray(rgb, dtype=np.float32) / 255.0
    lin = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    # sRGB -> XYZ (D65)
    x = lin[..., 0] * 0.4124564 + lin[..., 1] * 0.3575761 + lin[..., 2] * 0.1804375
    y = lin[..., 0] * 0.2126729 + lin[..., 1] * 0.7151522 + lin[..., 2] * 0.0721750
    z = lin[..., 0] * 0.0193339 + lin[..., 1] * 0.1191920 + lin[..., 2] * 0.9503041
    xyz = np.stack([x / 0.95047, y / 1.00000, z / 1.08883], axis=-1)
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    f = np.where(xyz > eps, np.cbrt(np.maximum(xyz, 0.0)), (kappa * xyz + 16.0) / 116.0)
    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1).astype(np.float32)


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    """Convert float32 CIE L*a*b* (D65) to uint8 sRGB image."""
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16.0) / 116.0
    fx = a / 500.0 + fy
    fz = fy - b / 200.0
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    xr = np.where(fx ** 3 > eps, fx ** 3, (116.0 * fx - 16.0) / kappa)
    yr = np.where(L > kappa * eps, ((L + 16.0) / 116.0) ** 3, L / kappa)
    zr = np.where(fz ** 3 > eps, fz ** 3, (116.0 * fz - 16.0) / kappa)
    x, y, z = xr * 0.95047, yr * 1.00000, zr * 1.08883
    r_lin = x * 3.2404542 - y * 1.5371385 - z * 0.4985314
    g_lin = -x * 0.9692660 + y * 1.8760108 + z * 0.0415560
    b_lin = x * 0.0556434 - y * 0.2040259 + z * 1.0572252
    lin = np.clip(np.stack([r_lin, g_lin, b_lin], axis=-1), 0.0, 1.0)
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * (lin ** (1.0 / 2.4)) - 0.055)
    return np.clip(np.rint(srgb * 255.0), 0, 255).astype(np.uint8)


def blend_seasonal_chroma(
    ortho_rgb: np.ndarray,
    season_rgb: np.ndarray,
    mask: np.ndarray | None = None,
    chroma_strength: float = 0.9,
    lightness_blend: float = 0.25,
) -> np.ndarray:
    """Transfer seasonal Lab chroma (and partial L*) onto high-res ortho texture."""
    ortho_lab = srgb_to_lab(ortho_rgb)
    season_lab = srgb_to_lab(season_rgb)

    out_lab = ortho_lab.copy()
    w = np.ones(ortho_rgb.shape[:2], dtype=np.float32) if mask is None else np.clip(mask.astype(np.float32), 0.0, 1.0)
    lw = w * lightness_blend
    cw = w * chroma_strength
    out_lab[..., 0] = ortho_lab[..., 0] * (1.0 - lw) + season_lab[..., 0] * lw
    out_lab[..., 1] = ortho_lab[..., 1] * (1.0 - cw) + season_lab[..., 1] * cw
    out_lab[..., 2] = ortho_lab[..., 2] * (1.0 - cw) + season_lab[..., 2] * cw
    return lab_to_srgb(out_lab)


def scl_clear_ratio(scl: np.ndarray) -> float:
    """Return fraction of pixels not classified as cloud/cirrus/cloud-shadow (SCL 3, 8, 9, 10)."""
    cloudy = np.isin(scl, [3, 8, 9, 10])
    return float(1.0 - np.mean(cloudy))


def search_sentinel2_scene(
    bbox_deg: tuple[float, float, float, float],
    datetime_range: str,
    max_cloud: float = 35.0,
) -> dict[str, Any]:
    """Query Element84 Earth Search and pick the scene clearest specifically inside bbox_deg."""
    body = json.dumps(
        {
            "collections": ["sentinel-2-l2a"],
            "bbox": list(bbox_deg),
            "datetime": datetime_range,
            "query": {"eo:cloud_cover": {"lt": max_cloud}},
            "limit": 12,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        STAC_SEARCH_URL,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    res = json.loads(_urlopen_retry(req).decode("utf-8"))
    feats = res.get("features") or []
    if not feats:
        raise RuntimeError(f"No Sentinel-2 L2A scene found for {datetime_range} (cloud < {max_cloud}%)")
    feats.sort(key=lambda f: float(f["properties"].get("eo:cloud_cover", 100.0)))

    best_feat = feats[0]
    best_clear = -1.0
    for feat in feats[:6]:
        scl_asset = feat.get("assets", {}).get("scl")
        if not scl_asset:
            continue
        epsg = int(feat["properties"]["proj:epsg"])
        scl_arr = read_cog_mercator_bbox(scl_asset["href"], epsg, scl_asset["proj:transform"], bbox_deg, 64, 64)
        clear = scl_clear_ratio(scl_arr)
        if clear > best_clear:
            best_clear = clear
            best_feat = feat
        if clear >= 0.99:
            break
    return best_feat


def read_cog_mercator_bbox(
    url: str,
    src_epsg: int,
    transform: list[float],
    bbox_deg: tuple[float, float, float, float],
    out_w: int,
    out_h: int,
) -> np.ndarray:
    """Fetch only intersecting COG tiles via HTTP Range and resample onto EPSG:3857 bbox grid."""
    ifd = parse_tiff_ifd(_http_range(url, 0, 32767))
    tw, th = ifd["tile_w"], ifd["tile_h"]
    tiles_x = math.ceil(ifd["width"] / tw)
    samples = ifd["samples_per_pixel"]
    bps = max(1, ifd["bits_per_sample"] // 8)

    tr_4326_to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x_min, y_min = tr_4326_to_3857.transform(bbox_deg[0], bbox_deg[1])
    x_max, y_max = tr_4326_to_3857.transform(bbox_deg[2], bbox_deg[3])

    xs_3857 = np.linspace(x_min, x_max, out_w, endpoint=False) + (x_max - x_min) / (2.0 * out_w)
    ys_3857 = np.linspace(y_max, y_min, out_h, endpoint=False) - (y_max - y_min) / (2.0 * out_h)
    gx, gy = np.meshgrid(xs_3857, ys_3857)

    tr_3857_to_src = Transformer.from_crs("EPSG:3857", f"EPSG:{src_epsg}", always_xy=True)
    sx, sy = tr_3857_to_src.transform(gx, gy)
    px_res, _, origin_x, _, py_res, origin_y = transform[:6]
    col_f = (sx - origin_x) / px_res
    row_f = (sy - origin_y) / py_res

    c0 = max(0, int(math.floor(float(np.min(col_f)))) - 1)
    c1 = min(ifd["width"] - 1, int(math.ceil(float(np.max(col_f)))) + 1)
    r0 = max(0, int(math.floor(float(np.min(row_f)))) - 1)
    r1 = min(ifd["height"] - 1, int(math.ceil(float(np.max(row_f)))) + 1)

    tx0, tx1 = c0 // tw, c1 // tw
    ty0, ty1 = r0 // th, r1 // th

    patch_w = (tx1 - tx0 + 1) * tw
    patch_h = (ty1 - ty0 + 1) * th
    dtype = np.uint16 if bps == 2 else np.uint8
    patch = np.zeros((patch_h, patch_w, samples), dtype=dtype)

    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            idx = ty * tiles_x + tx
            off = ifd["tile_offsets"][idx]
            cnt = ifd["tile_byte_counts"][idx]
            if cnt == 0:
                continue
            comp = _http_range(url, off, off + cnt - 1)
            tile_arr = decode_deflate_rgb_tile(comp, tw, th, samples=samples, predictor=ifd["predictor"], bytes_per_sample=bps)
            y0_p, x0_p = (ty - ty0) * th, (tx - tx0) * tw
            patch[y0_p : y0_p + th, x0_p : x0_p + tw] = tile_arr

    rel_r = row_f - ty0 * th
    rel_c = col_f - tx0 * tw
    out = np.zeros((out_h, out_w, samples), dtype=np.float32)
    for ch in range(samples):
        out[..., ch] = map_coordinates(patch[..., ch].astype(np.float32), [rel_r, rel_c], order=1, mode="nearest")
    return out.astype(dtype) if samples > 1 else out[..., 0]


def fetch_gsi_ortho_mosaic(bbox_deg: tuple[float, float, float, float], zoom: int = 16) -> tuple[np.ndarray, list[float]]:
    """Fetch GSI seamlessphoto tiles covering bbox_deg and return (RGB array, actual [w,s,e,n] bounds)."""
    def deg2num(lon: float, lat: float) -> tuple[int, int]:
        n = 2 ** zoom
        tx = int((lon + 180.0) / 360.0 * n)
        lat_r = math.radians(lat)
        ty = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
        return tx, ty

    def num2deg(tx: int, ty: int) -> tuple[float, float]:
        n = 2 ** zoom
        lon = tx / n * 360.0 - 180.0
        lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * ty / n))))
        return lon, lat

    import http.client
    import io
    x0, y1 = deg2num(bbox_deg[0], bbox_deg[1])
    x1, y0 = deg2num(bbox_deg[2], bbox_deg[3])
    canvas = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256))
    conn = http.client.HTTPSConnection("cyberjapandata.gsi.go.jp", timeout=20)
    try:
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                path = f"/xyz/seamlessphoto/{zoom}/{tx}/{ty}.jpg"
                for attempt in range(3):
                    try:
                        conn.request("GET", path, headers={"User-Agent": USER_AGENT, "Connection": "keep-alive"})
                        resp = conn.getresponse()
                        data = resp.read()
                        if resp.status != 200:
                            raise RuntimeError(f"GSI tile HTTP {resp.status}: {path}")
                        tile = Image.open(io.BytesIO(data)).convert("RGB")
                        canvas.paste(tile, ((tx - x0) * 256, (ty - y0) * 256))
                        break
                    except Exception:
                        conn.close()
                        conn = http.client.HTTPSConnection("cyberjapandata.gsi.go.jp", timeout=20)
                        if attempt == 2:
                            raise
                        time.sleep(0.4 * (attempt + 1))
    finally:
        conn.close()
    w_deg, n_deg = num2deg(x0, y0)
    e_deg, s_deg = num2deg(x1 + 1, y1 + 1)
    return np.asarray(canvas, dtype=np.uint8), [w_deg, s_deg, e_deg, n_deg]


def build_vegetation_mask(red: np.ndarray, nir: np.ndarray, ndvi_threshold: float = 0.22) -> np.ndarray:
    """Compute smooth [0, 1] vegetation weight from Sentinel-2 Red and NIR bands."""
    r = red.astype(np.float32)
    n = nir.astype(np.float32)
    ndvi = (n - r) / np.maximum(n + r, 1.0)
    raw_mask = np.clip((ndvi - ndvi_threshold) / 0.25, 0.0, 1.0)
    return gaussian_filter(raw_mask, sigma=1.5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build seasonal ortho textures from GSI + Sentinel-2 L2A.")
    parser.add_argument("--bbox", required=True, help="west,south,east,north in degrees")
    parser.add_argument("--zoom", type=int, default=16, help="GSI seamlessphoto zoom level")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument(
        "--season",
        action="append",
        required=True,
        help="name=START/END (e.g. summer=2024-07-15T00:00:00Z/2024-08-31T23:59:59Z)",
    )
    args = parser.parse_args(argv)

    parts = [float(x.strip()) for x in args.bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must have 4 comma-separated floats")
    req_bbox = (parts[0], parts[1], parts[2], parts[3])

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ortho_rgb, actual_bounds = fetch_gsi_ortho_mosaic(req_bbox, zoom=args.zoom)
    h, w = ortho_rgb.shape[:2]
    Image.fromarray(ortho_rgb).save(out_dir / "ortho_base.jpg", quality=92)
    bounds_tuple = (actual_bounds[0], actual_bounds[1], actual_bounds[2], actual_bounds[3])

    # Build a stable vegetation mask from summer Sentinel-2 NDVI if available, else each scene's NDVI
    manifest: dict[str, Any] = {
        "bounds": actual_bounds,
        "width": w,
        "height": h,
        "gsiZoom": args.zoom,
        "seasons": {},
    }

    summer_mask: np.ndarray | None = None
    parsed_seasons: list[tuple[str, str]] = []
    for item in args.season:
        name, dt = item.split("=", 1)
        parsed_seasons.append((name.strip(), dt.strip()))

    # Prefer summer scene's NDVI as vegetation mask so winter_burn still masks grass vs roads!
    for name, dt in parsed_seasons:
        if "summer" in name:
            feat = search_sentinel2_scene(bounds_tuple, dt, max_cloud=25.0)
            epsg = int(feat["properties"]["proj:epsg"])
            red = read_cog_mercator_bbox(feat["assets"]["red"]["href"], epsg, feat["assets"]["red"]["proj:transform"], bounds_tuple, w, h)
            nir = read_cog_mercator_bbox(feat["assets"]["nir"]["href"], epsg, feat["assets"]["nir"]["proj:transform"], bounds_tuple, w, h)
            summer_mask = build_vegetation_mask(red, nir)
            break

    for name, dt in parsed_seasons:
        feat = search_sentinel2_scene(bounds_tuple, dt, max_cloud=25.0)
        epsg = int(feat["properties"]["proj:epsg"])
        vis = feat["assets"]["visual"]
        season_rgb = read_cog_mercator_bbox(vis["href"], epsg, vis["proj:transform"], bounds_tuple, w, h).astype(np.uint8)
        mask = summer_mask
        if mask is None:
            red = read_cog_mercator_bbox(feat["assets"]["red"]["href"], epsg, feat["assets"]["red"]["proj:transform"], bounds_tuple, w, h)
            nir = read_cog_mercator_bbox(feat["assets"]["nir"]["href"], epsg, feat["assets"]["nir"]["proj:transform"], bounds_tuple, w, h)
            mask = build_vegetation_mask(red, nir)
        blended = blend_seasonal_chroma(ortho_rgb, season_rgb, mask=mask, chroma_strength=0.92, lightness_blend=0.30)
        out_file = out_dir / f"{name}.jpg"
        Image.fromarray(blended).save(out_file, quality=92)
        manifest["seasons"][name] = {
            "file": out_file.name,
            "sceneId": feat["id"],
            "datetime": feat["properties"]["datetime"],
            "cloudCover": feat["properties"]["eo:cloud_cover"],
        }
        print(f"[{name}] {feat['id']} ({feat['properties']['datetime'][:10]}) -> {out_file}")

    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
