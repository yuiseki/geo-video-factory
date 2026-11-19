#!/usr/bin/env python3
"""Generate virtual location scouting JSONs per 3D-building area with all river layers turned on."""

from __future__ import annotations
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
RESEARCH_DIR = PROJECT_DIR / "research" / "outputs"
SHOTS_DIR = PROJECT_DIR / "flyover" / "shots"

AREAS = {
    "shibuya": (139.692, 35.652, 139.710, 35.667),
    "ginza": (139.756, 35.660, 139.778, 35.678),
    "nihonbashi": (139.766, 35.676, 139.792, 35.696),
    "asakusa": (139.782, 35.698, 139.812, 35.726),
}


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


def select_features(feats: list[dict], bbox: tuple[float, float, float, float], max_count: int = 80) -> list[dict]:
    out = []
    for ft in feats:
        coords = feature_coords(ft)
        if coords and bbox_intersects(coords, bbox):
            p = ft["properties"]
            score = float(p.get("length_m") or 0) + float(p.get("area_m2") or 0) * 0.1
            out.append((score, ft))
    out.sort(key=lambda x: x[0], reverse=True)
    return [ft for _, ft in out[:max_count]]


def to_line_overlays(feats: list[dict], color: str, width: int = 6) -> list[dict]:
    return [
        {"type": "line", "coords": ft["geometry"]["coordinates"], "color": color, "width": width}
        for ft in feats if ft["geometry"]["type"] == "LineString"
    ]


def to_poly_overlays(feats: list[dict], fill: str, fill_opacity: float = 0.72, outline: str = "#ffffff", width: int = 3) -> list[dict]:
    res = []
    for ft in feats:
        if ft["geometry"]["type"] != "Polygon":
            continue
        ring = ft["geometry"]["coordinates"][0]
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        res.append({"type": "polygon", "coords": ring, "fill": fill, "fillOpacity": fill_opacity, "outline": outline, "width": width})
    return res


def tag_screen(text: str) -> list[int]:
    return [max(340, 40 + len(text) * 14), 55]


def all_river_overlays(bbox: tuple[float, float, float, float], f01, f02, f03, f04, f05) -> list[dict]:
    return (
        to_line_overlays(select_features(f01, bbox, 30), "#2dd4bf", 4)
        + to_line_overlays(select_features(f02, bbox, 45), "#38bdf8", 7)
        + to_poly_overlays(select_features(f03, bbox, 55), "#0ea5e9", 0.72, "#ffffff", 3)
        + to_line_overlays(select_features(f04, bbox, 20), "#f59e0b", 6)
        + to_poly_overlays(select_features(f05, bbox, 20), "#818cf8", 0.55, "#c7d2fe", 2)
    )


def build_area_doc(area: str, shots: list[dict]) -> dict:
    return {
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
            {"manifest": f"assets/buildings-3d/{area}/manifest.json", "heightOffset": -39, "workers": 3},
        ],
        "shots": shots,
    }


def main() -> None:
    f01 = load_geojson("01_current_rivers.geojson")
    f02 = load_geojson("02_culvert_and_valleys.geojson")
    f03 = load_geojson("03_filled_canals.geojson")
    f04 = load_geojson("04_old_aqueducts.geojson")
    f05 = load_geojson("05_former_channels.geojson")

    # 1. Shibuya scouting
    b = AREAS["shibuya"]
    base_ov = all_river_overlays(b, f01, f02, f03, f04, f05)
    shibuya_shots = [
        {
            "duration": 3,
            "from": {"center": [139.6992, 35.6602], "zoom": 16.6, "pitch": 68, "bearing": 35},
            "to": {"center": [139.7016, 35.6584], "zoom": 15.8, "pitch": 58, "bearing": 10},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("A1｜渋谷センター街・低空アオリ→合流点引き"), "text": "A1｜渋谷センター街・低空アオリ→合流点引き", "style": "tag"},
                {"type": "label", "at": [139.7016, 35.6580], "text": "渋谷川（暗渠）", "dot": True},
                {"type": "label", "at": [139.6986, 35.6618], "text": "宇田川（暗渠）", "dot": True},
            ],
        },
        {
            "duration": 3,
            "from": {"center": [139.7030, 35.6555], "zoom": 16.3, "pitch": 64, "bearing": -15},
            "to": {"center": [139.7035, 35.6625], "zoom": 16.0, "pitch": 58, "bearing": 5},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("A2｜渋谷駅直下・明治通り沿い縦断トラッキング"), "text": "A2｜渋谷駅直下・明治通り沿い縦断トラッキング", "style": "tag"},
                {"type": "label", "at": [139.7025, 35.6590], "text": "旧渋谷川（明治通り）", "dot": True},
            ],
        },
        {
            "duration": 3,
            "from": {"center": [139.6960, 35.6635], "zoom": 15.8, "pitch": 48, "bearing": 120},
            "to": {"center": [139.7010, 35.6595], "zoom": 15.4, "pitch": 45, "bearing": 140},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("A3｜代々木公園側・宇田川上流からの俯瞰"), "text": "A3｜代々木公園側・宇田川上流からの俯瞰", "style": "tag"},
            ],
        },
    ]

    # 2. Ginza scouting
    b = AREAS["ginza"]
    base_ov = all_river_overlays(b, f01, f02, f03, f04, f05)
    ginza_shots = [
        {
            "duration": 3,
            "from": {"center": [139.7652, 35.6682], "zoom": 16.6, "pitch": 65, "bearing": 28},
            "to": {"center": [139.7685, 35.6725], "zoom": 16.2, "pitch": 60, "bearing": 28},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("B1｜銀座・三十間堀 縦断ローアングル"), "text": "B1｜銀座・三十間堀 縦断ローアングル", "style": "tag"},
                {"type": "label", "at": [139.7670, 35.6700], "text": "三十間堀", "dot": True},
            ],
        },
        {
            "duration": 3,
            "from": {"center": [139.7635, 35.6685], "zoom": 16.3, "pitch": 60, "bearing": 45},
            "to": {"center": [139.7670, 35.6705], "zoom": 15.4, "pitch": 50, "bearing": -15},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("B2｜KK線（東京高速道路）カーブリビール"), "text": "B2｜KK線（東京高速道路）カーブリビール", "style": "tag"},
                {"type": "label", "at": [139.7630, 35.6710], "text": "外濠川・京橋川", "dot": True},
            ],
        },
        {
            "duration": 3,
            "from": {"center": [139.7720, 35.6655], "zoom": 16.0, "pitch": 55, "bearing": -25},
            "to": {"center": [139.7705, 35.6715], "zoom": 15.5, "pitch": 48, "bearing": -35},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("B3｜築地川（首都高C1下）〜桜川合流"), "text": "B3｜築地川（首都高C1下）〜桜川合流", "style": "tag"},
                {"type": "label", "at": [139.7720, 35.6680], "text": "築地川", "dot": True},
            ],
        },
    ]

    # 3. Nihonbashi scouting
    b = AREAS["nihonbashi"]
    base_ov = all_river_overlays(b, f01, f02, f03, f04, f05)
    nihonbashi_shots = [
        {
            "duration": 3,
            "from": {"center": [139.7795, 35.6865], "zoom": 16.3, "pitch": 58, "bearing": 165},
            "to": {"center": [139.7790, 35.6835], "zoom": 15.8, "pitch": 52, "bearing": 175},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("C1｜人形町・東堀留川＆西堀留川「2本の入堀」"), "text": "C1｜人形町・東堀留川＆西堀留川「2本の入堀」", "style": "tag"},
                {"type": "label", "at": [139.7800, 35.6845], "text": "東堀留川", "dot": True},
                {"type": "label", "at": [139.7782, 35.6845], "text": "西堀留川", "dot": True},
            ],
        },
        {
            "duration": 3,
            "from": {"center": [139.7765, 35.6820], "zoom": 16.4, "pitch": 64, "bearing": 195},
            "to": {"center": [139.7745, 35.6780], "zoom": 15.9, "pitch": 58, "bearing": 190},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("C2｜楓川（江戸橋JCT〜首都高C1下）縦断"), "text": "C2｜楓川（江戸橋JCT〜首都高C1下）縦断", "style": "tag"},
                {"type": "label", "at": [139.7760, 35.6800], "text": "楓川", "dot": True},
            ],
        },
        {
            "duration": 3,
            "from": {"center": [139.7740, 35.6905], "zoom": 15.8, "pitch": 50, "bearing": 85},
            "to": {"center": [139.7830, 35.6890], "zoom": 15.4, "pitch": 46, "bearing": 70},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("C3｜龍閑川〜浜町川・隅田川への横の繋がり"), "text": "C3｜龍閑川〜浜町川・隅田川への横の繋がり", "style": "tag"},
                {"type": "label", "at": [139.7755, 35.6902], "text": "龍閑川", "dot": True},
                {"type": "label", "at": [139.7845, 35.6890], "text": "浜町川", "dot": True},
            ],
        },
    ]

    # 4. Asakusa / Taito scouting
    b = AREAS["asakusa"]
    base_ov = all_river_overlays(b, f01, f02, f03, f04, f05)
    asakusa_shots = [
        {
            "duration": 3,
            "from": {"center": [139.7975, 35.7215], "zoom": 16.2, "pitch": 62, "bearing": 125},
            "to": {"center": [139.8045, 35.7165], "zoom": 15.7, "pitch": 56, "bearing": 115},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("D1｜山谷堀（吉原大門→隅田川・待乳山聖天）縦断"), "text": "D1｜山谷堀（吉原大門→隅田川・待乳山聖天）縦断", "style": "tag"},
                {"type": "label", "at": [139.8020, 35.7180], "text": "山谷堀", "dot": True},
            ],
        },
        {
            "duration": 3,
            "from": {"center": [139.7860, 35.7025], "zoom": 16.1, "pitch": 56, "bearing": 10},
            "to": {"center": [139.7875, 35.7075], "zoom": 15.7, "pitch": 50, "bearing": 25},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("D2｜三味線堀（鳥越〜新堀通り）街区リビール"), "text": "D2｜三味線堀（鳥越〜新堀通り）街区リビール", "style": "tag"},
                {"type": "label", "at": [139.7865, 35.7045], "text": "三味線堀", "dot": True},
            ],
        },
        {
            "duration": 3,
            "from": {"center": [139.7960, 35.7120], "zoom": 15.4, "pitch": 64, "bearing": 70},
            "to": {"center": [139.8010, 35.7145], "zoom": 15.1, "pitch": 58, "bearing": 85},
            "overlays": base_ov + [
                {"type": "label", "screen": tag_screen("D3｜浅草寺北側・山谷堀から隅田川遠望"), "text": "D3｜浅草寺北側・山谷堀から隅田川遠望", "style": "tag"},
            ],
        },
    ]

    mapping = {
        "shibuya": shibuya_shots,
        "ginza": ginza_shots,
        "nihonbashi": nihonbashi_shots,
        "asakusa": asakusa_shots,
    }
    for area, shots in mapping.items():
        p = SHOTS_DIR / f"scout_{area}.json"
        p.write_text(json.dumps(build_area_doc(area, shots), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(shots)} scouting shots to {p}")


if __name__ == "__main__":
    main()
