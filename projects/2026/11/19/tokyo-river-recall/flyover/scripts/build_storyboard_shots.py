#!/usr/bin/env python3
"""Generate dynamic camera storyboard shots (v03) showing visual reveals from street-level surprises to macro network."""

from __future__ import annotations
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
RESEARCH_DIR = PROJECT_DIR / "research" / "outputs"
OUT_PATH = PROJECT_DIR / "flyover" / "shots" / "storyboard.json"


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


def select_features(
    feats: list[dict],
    bbox: tuple[float, float, float, float] | None = None,
    max_count: int = 80,
    min_len_m: float = 0.0,
    category: str | None = None,
) -> list[dict]:
    out = []
    for ft in feats:
        p = ft["properties"]
        if category and p.get("category") != category:
            continue
        length = float(p.get("length_m") or 0.0)
        area = float(p.get("area_m2") or 0.0)
        if min_len_m > 0 and length < min_len_m and area == 0:
            continue
        coords = feature_coords(ft)
        if not coords:
            continue
        if bbox and not bbox_intersects(coords, bbox):
            continue
        out.append((length + area * 0.1, ft))
    out.sort(key=lambda x: x[0], reverse=True)
    return [ft for _, ft in out[:max_count]]


def to_line_overlays(
    feats: list[dict],
    color: str,
    width: int = 3,
    draw: list[float] | None = None,
    show: list[float] | None = None,
) -> list[dict]:
    res = []
    for ft in feats:
        if ft["geometry"]["type"] != "LineString":
            continue
        item: dict = {
            "type": "line",
            "coords": ft["geometry"]["coordinates"],
            "color": color,
            "width": width,
        }
        if draw is not None:
            item["draw"] = draw
        if show is not None:
            item["show"] = show
        res.append(item)
    return res


def to_poly_overlays(
    feats: list[dict],
    fill: str,
    fill_opacity: float = 0.5,
    outline: str = "#ffffff",
    width: int = 2,
    show: list[float] | None = None,
) -> list[dict]:
    res = []
    for ft in feats:
        if ft["geometry"]["type"] != "Polygon":
            continue
        ring = ft["geometry"]["coordinates"][0]
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        item: dict = {
            "type": "polygon",
            "coords": ring,
            "fill": fill,
            "fillOpacity": fill_opacity,
            "outline": outline,
            "width": width,
        }
        if show is not None:
            item["show"] = show
        res.append(item)
    return res


def tag_screen(text: str) -> list[int]:
    return [max(320, 40 + len(text) * 14), 55]


def ui_header(tag: str, counter_val: float | str, counter_from: float | None = None, caption: str = "復活した川（累計）", unit: str = "km") -> list[dict]:
    c: dict = {
        "type": "counter",
        "screen": [1460, 55],
        "caption": caption,
        "value": counter_val,
        "decimals": 2 if isinstance(counter_val, float) else 0,
        "unit": unit,
    }
    if counter_from is not None:
        c["from"] = counter_from
        c["countUp"] = [0.15, 0.85]
    return [
        {"type": "label", "screen": tag_screen(tag), "text": tag, "style": "tag"},
        c,
    ]


def main() -> None:
    f01 = load_geojson("01_current_rivers.geojson")
    f02 = load_geojson("02_culvert_and_valleys.geojson")
    f03 = load_geojson("03_filled_canals.geojson")
    f04 = load_geojson("04_old_aqueducts.geojson")
    f05 = load_geojson("05_former_channels.geojson")
    f06 = load_geojson("06_flood_overlap.geojson")

    C_CURR = "#2dd4bf"
    C_CULV = "#38bdf8"
    C_VAL = "#7dd3fc"
    C_CANAL = "#0ea5e9"
    C_AQUED = "#f59e0b"
    C_FORMER = "#818cf8"
    C_FLOOD = "#fb7185"

    TOKYO_BBOX = (139.55, 35.53, 139.93, 35.82)
    SHIBUYA_BBOX = (139.67, 35.64, 139.73, 35.68)
    GINZA_BBOX = (139.74, 35.65, 139.79, 35.70)
    NIHONBASHI_BBOX = (139.75, 35.66, 139.80, 35.70)
    SHITAMACHI_BBOX = (139.77, 35.67, 139.87, 35.74)
    YAMANOTE_BBOX = (139.58, 35.59, 139.76, 35.79)
    ARAKAWA_BBOX = (139.74, 35.72, 139.90, 35.82)
    TAMAGAWA_BBOX = (139.60, 35.53, 139.78, 35.62)

    shots = []

    # Shot 01: Street-level Shibuya Center-gai -> Orbit & pull back to reveal Shibuya/Udagawa confluence
    shots.append({
        "duration": 3,
        "from": {"center": [139.6992, 35.6604], "zoom": 16.5, "pitch": 68, "bearing": 35},
        "to": {"center": [139.7016, 35.6580], "zoom": 14.8, "pitch": 50, "bearing": -10},
        "overlays": (
            to_line_overlays(select_features(f01, SHIBUYA_BBOX, 20), C_CURR, 4)
            + to_line_overlays(select_features(f02, SHIBUYA_BBOX, 40), C_CULV, 6, draw=[0.2, 0.75], show=[0.2, 1])
            + [
                {"type": "label", "screen": tag_screen("Shot 01｜OP：センター街の真下から引くと川の合流点"), "text": "Shot 01｜OP：センター街の真下から引くと川の合流点", "style": "tag"},
                {"type": "label", "at": [139.7016, 35.6580], "text": "渋谷川（暗渠）", "dot": True, "show": [0.4, 1]},
                {"type": "label", "at": [139.6986, 35.6618], "text": "宇田川（暗渠）", "dot": True, "show": [0.4, 1]},
                {"type": "note", "text": "オープンデータによる再現イメージ（位置は概略）"},
            ]
        ),
    })

    # Shot 02: Fly out from Shibuya to 23-ku overview (Current rivers only)
    shots.append({
        "duration": 3,
        "path": "fly",
        "from": {"center": [139.7016, 35.6580], "zoom": 14.0, "pitch": 48, "bearing": -10},
        "to": {"center": [139.74, 35.68], "zoom": 10.6, "pitch": 30, "bearing": 0},
        "overlays": (
            to_line_overlays(select_features(f01, TOKYO_BBOX, 100, min_len_m=400), C_CURR, 3)
            + ui_header("Shot 02｜OP：渋谷から引くと、今の川はこれだけ", 369.79, caption="現行開渠河川")
        ),
    })

    # Shot 03: Slow pan across Tokyo with Open Data promise
    shots.append({
        "duration": 3,
        "from": {"center": [139.71, 35.67], "zoom": 10.9, "pitch": 35, "bearing": -8},
        "to": {"center": [139.77, 35.69], "zoom": 10.7, "pitch": 30, "bearing": 5},
        "overlays": (
            to_line_overlays(select_features(f01, TOKYO_BBOX, 100, min_len_m=400), C_CURR, 3)
            + [
                {"type": "label", "screen": tag_screen("Shot 03｜OP：商用可オープンデータのみで4段階復元"), "text": "Shot 03｜OP：商用可オープンデータのみで4段階復元", "style": "tag"},
                {"type": "quote", "source": "使用データ方針", "text": "国土地理院・OSM・国土数値情報・東京都オープンデータのみ使用（下水道台帳・民間古地図は不使用）", "marks": False, "screen": [70, 150], "width": 760},
            ]
        ),
    })

    # Shot 04: Ch1 Yamanote - Dolly along Setagaya/Meguro valleys (terrain reveal)
    shots.append({
        "duration": 3,
        "from": {"center": [139.63, 35.63], "zoom": 13.0, "pitch": 58, "bearing": 40},
        "to": {"center": [139.67, 35.66], "zoom": 11.7, "pitch": 48, "bearing": 15},
        "overlays": (
            to_line_overlays(select_features(f01, YAMANOTE_BBOX, 40, min_len_m=300), C_CURR, 2)
            + ui_header("Shot 04｜第1章：一見平らな住宅街、実は無数の「谷」", 0.0, caption="復活した川（累計）")
            + [{"type": "label", "at": [139.64, 35.64], "text": "目黒川が削った谷筋", "dot": True}]
        ),
    })

    # Shot 05: Ch1 Culverts & Valleys draw across Yamanote while tilting up
    shots.append({
        "duration": 3,
        "from": {"center": [139.64, 35.64], "zoom": 12.2, "pitch": 45, "bearing": 10},
        "to": {"center": [139.67, 35.67], "zoom": 11.4, "pitch": 36, "bearing": 0},
        "overlays": (
            to_line_overlays(select_features(f01, YAMANOTE_BBOX, 40, min_len_m=300), C_CURR, 2)
            + to_line_overlays(select_features(f02, YAMANOTE_BBOX, 80, min_len_m=600, category="culvert_osm"), C_CULV, 4, draw=[0.1, 0.8])
            + to_line_overlays(select_features(f02, YAMANOTE_BBOX, 60, min_len_m=800, category="valley_dem"), C_VAL, 2, draw=[0.2, 0.85])
            + ui_header("Shot 05｜第1章：暗渠と谷筋が一斉に蘇る（+384.31km）", 384.31, counter_from=0.0)
        ),
    })

    # Shot 06: Ch1 Basin comparison chart + Meguro River tracking
    shots.append({
        "duration": 3,
        "from": {"center": [139.69, 35.63], "zoom": 12.8, "pitch": 42, "bearing": -25},
        "to": {"center": [139.65, 35.65], "zoom": 12.2, "pitch": 35, "bearing": -10},
        "overlays": (
            to_line_overlays(select_features(f01, YAMANOTE_BBOX, 30, min_len_m=300), C_CURR, 2)
            + to_line_overlays(select_features(f02, YAMANOTE_BBOX, 60, min_len_m=700), C_CULV, 4)
            + [
                {"type": "label", "screen": tag_screen("Shot 06｜第1章：目黒川水系は87.9kmが地下・谷"), "text": "Shot 06｜第1章：目黒川水系は87.9kmが地下・谷", "style": "tag"},
                {"type": "panel", "src": "assets/fig2_basin_comparison.png", "caption": "主要水系別：現行開渠 vs 暗渠・谷筋", "credit": "集計：summary.json", "screen": [1040, 140], "width": 810},
            ]
        ),
    })

    # Shot 07: Ch1 Modern Kitazawa-gawa greenway -> Reveal 1945 ort_USA10 aerial photo
    shots.append({
        "duration": 3,
        "from": {"center": [139.662, 35.656], "zoom": 16.0, "pitch": 35, "bearing": 20},
        "to": {"center": [139.670, 35.661], "zoom": 15.3, "pitch": 20, "bearing": 0},
        "overlays": (
            [{"type": "base", "layer": "ort_USA10", "show": [0.45, 1], "fade": 0.2}]
            + to_line_overlays(select_features(f02, (139.65, 35.645, 139.685, 35.675), 30), C_CULV, 4)
            + [
                {"type": "label", "screen": tag_screen("Shot 07｜第1章：現代の緑道→1945年空中写真で川を確認"), "text": "Shot 07｜第1章：現代の緑道→1945年空中写真で川を確認", "style": "tag"},
                {"type": "label", "at": [139.668, 35.660], "text": "北沢川（暗渠化前）", "dot": True},
                {"type": "note", "text": "1945〜50年 米軍撮影空中写真（国土地理院）／地名は現代のもの"},
            ]
        ),
    })

    # Shot 08: Ch1 -> Ch2 Dolly east along Kanda/Akasaka into flat central Tokyo
    shots.append({
        "duration": 3,
        "from": {"center": [139.70, 35.675], "zoom": 13.5, "pitch": 48, "bearing": 75},
        "to": {"center": [139.755, 35.675], "zoom": 13.3, "pitch": 42, "bearing": 50},
        "overlays": (
            to_line_overlays(select_features(f01, (139.68, 35.64, 139.79, 35.71), 40), C_CURR, 2)
            + to_line_overlays(select_features(f02, (139.68, 35.64, 139.79, 35.71), 60, min_len_m=400), C_CULV, 3)
            + ui_header("Shot 08｜第1章→第2章：山の手の谷を抜けて都心へ", 384.31)
        ),
    })

    # Shot 09: Ch2 Surprise! Close-up of Ginza/KK-line expressway (looks like pure concrete) -> Pull back
    shots.append({
        "duration": 3,
        "from": {"center": [139.766, 35.672], "zoom": 16.4, "pitch": 62, "bearing": 30},
        "to": {"center": [139.768, 35.673], "zoom": 14.3, "pitch": 48, "bearing": 15},
        "overlays": (
            to_line_overlays(select_features(f01, GINZA_BBOX, 30), C_CURR, 2)
            + ui_header("Shot 09｜第2章：高速道路と銀座のビル街…ここも川？", 384.31)
            + [{"type": "label", "at": [139.766, 35.673], "text": "東京高速道路（KK線）", "dot": True}]
        ),
    })

    # Shot 10: Ch2 Reveal! Ginza / Tsukiji / Shiodome canals flood back under expressways
    shots.append({
        "duration": 3,
        "from": {"center": [139.763, 35.666], "zoom": 15.6, "pitch": 54, "bearing": 25},
        "to": {"center": [139.770, 35.672], "zoom": 14.8, "pitch": 45, "bearing": 10},
        "overlays": (
            to_line_overlays(select_features(f01, GINZA_BBOX, 25), C_CURR, 2)
            + to_poly_overlays(select_features(f03, GINZA_BBOX, 50), C_CANAL, 0.58, "#ffffff", 2, show=[0.25, 1])
            + ui_header("Shot 10｜第2章：高速道路の下がすべて“掘割”に戻る！", 404.44, counter_from=384.31)
            + [
                {"type": "label", "at": [139.767, 35.670], "text": "三十間堀", "dot": True, "show": [0.35, 1]},
                {"type": "label", "at": [139.772, 35.667], "text": "築地川（首都高C1下）", "dot": True, "show": [0.4, 1]},
                {"type": "label", "at": [139.760, 35.664], "text": "汐留川", "dot": True, "show": [0.45, 1]},
            ]
        ),
    })

    # Shot 11: Ch2 Nihonbashi Ningyocho -> Switch to 1945 ort_USA10 showing real water in Horidome/Momijigawa
    shots.append({
        "duration": 3,
        "from": {"center": [139.778, 35.683], "zoom": 15.8, "pitch": 38, "bearing": -15},
        "to": {"center": [139.774, 35.678], "zoom": 14.9, "pitch": 25, "bearing": 0},
        "overlays": (
            [{"type": "base", "layer": "ort_USA10", "show": [0.45, 1], "fade": 0.2}]
            + to_poly_overlays(select_features(f03, NIHONBASHI_BBOX, 50), C_CANAL, 0.45, "#ffffff", 2)
            + [
                {"type": "label", "screen": tag_screen("Shot 11｜第2章：日本橋オフィス街→1945年の入堀と一致"), "text": "Shot 11｜第2章：日本橋オフィス街→1945年の入堀と一致", "style": "tag"},
                {"type": "label", "at": [139.776, 35.680], "text": "楓川", "dot": True},
                {"type": "label", "at": [139.779, 35.684], "text": "東堀留川・西堀留川", "dot": True},
                {"type": "note", "text": "1945〜50年 米軍撮影空中写真（国土地理院）／地名は現代のもの"},
            ]
        ),
    })

    # Shot 12: Ch2 Fly from Asakusa (Sanya-bori) across Sumida to Koto (Oyokogawa/Tatekawa)
    shots.append({
        "duration": 3,
        "from": {"center": [139.802, 35.716], "zoom": 15.0, "pitch": 55, "bearing": 145},
        "to": {"center": [139.818, 35.694], "zoom": 13.2, "pitch": 40, "bearing": 10},
        "overlays": (
            to_line_overlays(select_features(f01, SHITAMACHI_BBOX, 40), C_CURR, 2)
            + to_poly_overlays(select_features(f03, SHITAMACHI_BBOX, 50), C_CANAL, 0.58, "#ffffff", 2)
            + ui_header("Shot 12｜第2章：浅草・山谷堀から深川の親水公園網へ", 404.44)
            + [
                {"type": "label", "at": [139.802, 35.718], "text": "山谷堀", "dot": True},
                {"type": "label", "at": [139.814, 35.704], "text": "大横川親水公園", "dot": True, "show": [0.4, 1]},
                {"type": "label", "at": [139.825, 35.693], "text": "竪川河川敷公園", "dot": True, "show": [0.45, 1]},
            ]
        ),
    })

    # Shot 13: Ch3 Tracking along Tamagawa Josui ridge from west to Shinjuku
    shots.append({
        "duration": 3,
        "from": {"center": [139.615, 35.684], "zoom": 13.6, "pitch": 55, "bearing": 95},
        "to": {"center": [139.675, 35.676], "zoom": 12.6, "pitch": 46, "bearing": 35},
        "overlays": (
            to_line_overlays(select_features(f01, YAMANOTE_BBOX, 30, min_len_m=300), C_CURR, 2)
            + to_line_overlays(select_features(f02, YAMANOTE_BBOX, 50, min_len_m=700), C_CULV, 2)
            + to_line_overlays(select_features(f04, TOKYO_BBOX, 64), C_AQUED, 5, draw=[0.1, 0.85])
            + ui_header("Shot 13｜第3章：谷の逆！尾根の上を突っ走る玉川上水", 459.54, counter_from=404.44)
            + [{"type": "label", "at": [139.645, 35.676], "text": "玉川上水（分水嶺の尾根）", "dot": True}]
        ),
    })

    # Shot 14: Ch3 Pull back to show Senkawa & Rokugo aqueducts too
    shots.append({
        "duration": 3,
        "from": {"center": [139.675, 35.676], "zoom": 12.4, "pitch": 42, "bearing": 20},
        "to": {"center": [139.70, 35.66], "zoom": 11.1, "pitch": 34, "bearing": 0},
        "overlays": (
            to_line_overlays(select_features(f01, TOKYO_BBOX, 50, min_len_m=500), C_CURR, 2)
            + to_line_overlays(select_features(f02, TOKYO_BBOX, 60, min_len_m=800), C_CULV, 2)
            + to_poly_overlays(select_features(f03, TOKYO_BBOX, 40), C_CANAL, 0.5, "#ffffff", 1)
            + to_line_overlays(select_features(f04, TOKYO_BBOX, 64), C_AQUED, 4)
            + ui_header("Shot 14｜第3章：千川上水・六郷用水も加わり水網が完成", 459.54)
        ),
    })

    # Shot 15: Ch4 Dolly along straight Arakawa -> Reveal giant meandering former channels
    shots.append({
        "duration": 3,
        "from": {"center": [139.785, 35.755], "zoom": 13.4, "pitch": 52, "bearing": -20},
        "to": {"center": [139.815, 35.775], "zoom": 12.1, "pitch": 40, "bearing": 0},
        "overlays": (
            to_line_overlays(select_features(f01, ARAKAWA_BBOX, 40), C_CURR, 2)
            + to_poly_overlays(select_features(f05, ARAKAWA_BBOX, 80), C_FORMER, 0.6, "#c7d2fe", 2, show=[0.25, 1])
            + ui_header("Shot 15｜第4章：真っ直ぐな荒川の横に眠る巨大な蛇行跡", 5.84, caption="旧河道（治水地形分類図）", unit="km²")
            + [{"type": "label", "at": [139.805, 35.785], "text": "旧河道（暴れ川の跡）", "dot": True, "show": [0.35, 1]}]
        ),
    })

    # Shot 16: Ch4 Tamagawa former channels -> Fly out to all 23-ku
    shots.append({
        "duration": 3,
        "path": "fly",
        "from": {"center": [139.70, 35.565], "zoom": 13.2, "pitch": 45, "bearing": 20},
        "to": {"center": [139.74, 35.675], "zoom": 10.7, "pitch": 32, "bearing": 0},
        "overlays": (
            to_line_overlays(select_features(f01, TOKYO_BBOX, 40, min_len_m=500), C_CURR, 2)
            + to_line_overlays(select_features(f04, TOKYO_BBOX, 40), C_AQUED, 3)
            + to_poly_overlays(select_features(f05, TOKYO_BBOX, 60), C_FORMER, 0.55, "#c7d2fe", 2)
            + ui_header("Shot 16｜第4章：多摩川旧河道も含め、5層すべてが揃う", 459.54)
        ),
    })

    # Shot 17: Ending - Flood overlap reveal + chart
    shots.append({
        "duration": 3,
        "from": {"center": [139.72, 35.67], "zoom": 11.2, "pitch": 36, "bearing": -10},
        "to": {"center": [139.74, 35.68], "zoom": 10.6, "pitch": 30, "bearing": 0},
        "overlays": (
            to_line_overlays(select_features(f02, TOKYO_BBOX, 50, min_len_m=900), C_CULV, 2)
            + to_poly_overlays(select_features(f03, TOKYO_BBOX, 30), C_CANAL, 0.4, "#ffffff", 1)
            + to_poly_overlays(select_features(f05, TOKYO_BBOX, 40), C_FORMER, 0.4, "#c7d2fe", 1)
            + to_poly_overlays(select_features(f06, TOKYO_BBOX, 60), C_FLOOD, 0.55, "#fda4af", 1, show=[0.25, 1])
            + [
                {"type": "label", "screen": tag_screen("Shot 17｜終章：浸水実績の45.2%が元・川の100m以内"), "text": "Shot 17｜終章：浸水実績の45.2%が元・川の100m以内", "style": "tag"},
                {"type": "panel", "src": "assets/fig3_flood_overlap_validation.png", "caption": "浸水実績ポリゴンとの最短距離分布", "credit": "東京都浸水実績図（1974〜2019年）", "screen": [1080, 150], "width": 770},
            ]
        ),
    })

    # Shot 18: Ending - Slow orbit out over complete restored Tokyo
    shots.append({
        "duration": 3,
        "from": {"center": [139.74, 35.68], "zoom": 10.8, "pitch": 38, "bearing": -10},
        "to": {"center": [139.74, 35.68], "zoom": 10.3, "pitch": 28, "bearing": 10},
        "overlays": (
            to_line_overlays(select_features(f01, TOKYO_BBOX, 45, min_len_m=500), C_CURR, 2)
            + to_line_overlays(select_features(f02, TOKYO_BBOX, 65, min_len_m=800), C_CULV, 2)
            + to_poly_overlays(select_features(f03, TOKYO_BBOX, 45), C_CANAL, 0.55, "#ffffff", 1)
            + to_line_overlays(select_features(f04, TOKYO_BBOX, 50), C_AQUED, 3)
            + to_poly_overlays(select_features(f05, TOKYO_BBOX, 50), C_FORMER, 0.5, "#c7d2fe", 1)
            + [
                {"type": "label", "screen": tag_screen("Shot 18｜終章：すべてを重ねた「本来の東京」"), "text": "Shot 18｜終章：すべてを重ねた「本来の東京」", "style": "tag"},
                {
                    "type": "counter",
                    "screen": [1460, 110],
                    "caption": "復活した川（累計ライン）",
                    "value": 459.54,
                    "decimals": 2,
                    "unit": "km",
                },
                {"type": "note", "text": "全5層統合（復元ライン459.54km + 面6.83km²）※再現イメージ"},
            ]
        ),
    })

    doc = {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "base": "seamlessphoto",
        "dem": "gsi",
        "exaggeration": 1.6,
        "hillshade": 0.3,
        "saturation": -0.15,
        "contrast": 0.08,
        "credits": [
            "オープンデータによる再現イメージ（位置は概略）",
            "出典：OpenStreetMap contributors (ODbL-1.0) / 国土交通省 国土数値情報 / 東京都浸水実績図（CC BY 4.0）",
        ],
        "shots": shots,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(shots)} dynamic shots to {OUT_PATH}")


if __name__ == "__main__":
    main()
