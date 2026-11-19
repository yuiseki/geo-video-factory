#!/usr/bin/env python3
"""Generate 3D-building close-up storyboard shots (Shibuya & Ginza) with PLATEAU + city_proxy + pseudo-textures."""

from __future__ import annotations
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
RESEARCH_DIR = PROJECT_DIR / "research" / "outputs"
OUT_PATH = PROJECT_DIR / "flyover" / "shots" / "storyboard_3d_buildings.json"


def load_geojson(name: str) -> list[dict]:
    with open(RESEARCH_DIR / name, encoding="utf-8") as f:
        return json.load(f)["features"]


def bbox_intersects(coords: list, bbox: tuple[float, float, float, float]) -> bool:
    w, s, e, n = bbox
    xs = [p[0] for p in coords]
    ys = [p[1] for p in coords]
    return not (max(xs) < w or min(xs) > e or max(ys) < s or min(ys) > n)


def feature_coords(ft: dict) -> list:
    geom = ft["geometry"]
    if geom["type"] == "LineString":
        return geom["coordinates"]
    elif geom["type"] == "Polygon":
        return geom["coordinates"][0]
    return []


def select_features(feats: list[dict], bbox: tuple[float, float, float, float], max_count: int = 60) -> list[dict]:
    out = []
    for ft in feats:
        coords = feature_coords(ft)
        if coords and bbox_intersects(coords, bbox):
            p = ft["properties"]
            score = float(p.get("length_m") or 0) + float(p.get("area_m2") or 0) * 0.1
            out.append((score, ft))
    out.sort(key=lambda x: x[0], reverse=True)
    return [ft for _, ft in out[:max_count]]


def to_line_overlays(feats: list[dict], color: str, width: int = 6, draw: list[float] | None = None, show: list[float] | None = None) -> list[dict]:
    res = []
    for ft in feats:
        if ft["geometry"]["type"] != "LineString":
            continue
        item: dict = {"type": "line", "coords": ft["geometry"]["coordinates"], "color": color, "width": width}
        if draw is not None:
            item["draw"] = draw
        if show is not None:
            item["show"] = show
        res.append(item)
    return res


def to_poly_overlays(feats: list[dict], fill: str, fill_opacity: float = 0.65, outline: str = "#ffffff", width: int = 3, show: list[float] | None = None) -> list[dict]:
    res = []
    for ft in feats:
        if ft["geometry"]["type"] != "Polygon":
            continue
        ring = ft["geometry"]["coordinates"][0]
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        item: dict = {"type": "polygon", "coords": ring, "fill": fill, "fillOpacity": fill_opacity, "outline": outline, "width": width}
        if show is not None:
            item["show"] = show
        res.append(item)
    return res


def tag_screen(text: str) -> list[int]:
    return [max(320, 40 + len(text) * 14), 55]


def main() -> None:
    f01 = load_geojson("01_current_rivers.geojson")
    f02 = load_geojson("02_culvert_and_valleys.geojson")
    f03 = load_geojson("03_filled_canals.geojson")

    SHIBUYA_BBOX = (139.692, 35.652, 139.710, 35.667)
    GINZA_BBOX = (139.756, 35.660, 139.778, 35.678)

    shots = [
        # Shot 01: Shibuya 3D buildings + Shibuya/Udagawa culverts
        {
            "duration": 3,
            "from": {"center": [139.6995, 35.6602], "zoom": 16.6, "pitch": 62, "bearing": 35},
            "to": {"center": [139.7016, 35.6584], "zoom": 15.8, "pitch": 55, "bearing": 10},
            "overlays": (
                to_line_overlays(select_features(f01, SHIBUYA_BBOX, 15), "#2dd4bf", 5)
                + to_line_overlays(select_features(f02, SHIBUYA_BBOX, 35), "#38bdf8", 8, draw=[0.15, 0.75], show=[0.15, 1])
                + [
                    {"type": "label", "screen": tag_screen("Shot 01（3D建物版）｜渋谷センター街の足元を走る川"), "text": "Shot 01（3D建物版）｜渋谷センター街の足元を走る川", "style": "tag"},
                    {"type": "label", "at": [139.7016, 35.6580], "text": "渋谷川（暗渠）", "dot": True, "show": [0.35, 1]},
                    {"type": "label", "at": [139.6986, 35.6618], "text": "宇田川（暗渠）", "dot": True, "show": [0.35, 1]},
                    {"type": "note", "text": "3D建物：PLATEAU + 地理院・OSM補完（推定テクスチャ含む）"},
                ]
            ),
        },
        # Shot 10: Ginza / Shiodome / Tsukiji 3D buildings + filled canals
        {
            "duration": 3,
            "from": {"center": [139.7655, 35.6695], "zoom": 16.4, "pitch": 60, "bearing": 25},
            "to": {"center": [139.7685, 35.6695], "zoom": 15.5, "pitch": 50, "bearing": 10},
            "overlays": (
                to_line_overlays(select_features(f01, GINZA_BBOX, 20), "#2dd4bf", 3)
                + to_poly_overlays(select_features(f03, GINZA_BBOX, 45), "#0ea5e9", 0.7, "#ffffff", 3, show=[0.2, 1])
                + [
                    {"type": "label", "screen": tag_screen("Shot 10（3D建物版）｜銀座・高速道路の下に蘇る掘割"), "text": "Shot 10（3D建物版）｜銀座・高速道路の下に蘇る掘割", "style": "tag"},
                    {"type": "counter", "screen": [1460, 55], "caption": "復活した川（累計）", "from": 384.31, "value": 404.44, "decimals": 2, "unit": "km", "countUp": [0.2, 0.85]},
                    {"type": "label", "at": [139.7670, 35.6700], "text": "三十間堀", "dot": True, "show": [0.35, 1]},
                    {"type": "label", "at": [139.7720, 35.6670], "text": "築地川（首都高C1下）", "dot": True, "show": [0.4, 1]},
                    {"type": "note", "text": "3D建物：PLATEAU + 地理院・OSM補完（推定テクスチャ含む）"},
                ]
            ),
        },
    ]

    doc = {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "base": "seamlessphoto",
        "world": False,
        "dem": "gsi",
        "exaggeration": 1,
        "hillshade": 0.2,
        "credits": [
            "建物: 国土交通省 PLATEAU / 国土地理院ベクトルタイル / © OpenStreetMap contributors",
            "水路再現: オープンデータによる再現イメージ（位置は概略）",
        ],
        "plateauBuildings": [
            {"manifest": "assets/buildings-3d/shibuya/manifest.json", "heightOffset": -39, "workers": 3, "opacity": [[0, 1.0], [1.4, 0.38], [3, 0.38]]},
            {"manifest": "assets/buildings-3d/ginza/manifest.json", "heightOffset": -39, "workers": 3, "opacity": [[0, 1.0], [1.4, 0.38], [3, 0.38]]},
        ],
        "shots": shots,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(shots)} 3D shots to {OUT_PATH}")


if __name__ == "__main__":
    main()
