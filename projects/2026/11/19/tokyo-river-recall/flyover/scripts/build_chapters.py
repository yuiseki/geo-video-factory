#!/usr/bin/env python3
"""Build all narrated chapter shot JSONs and chapters.json manifest for tokyo-river-recall."""

from __future__ import annotations
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
RESEARCH_DIR = PROJECT_DIR / "research" / "outputs"
FLYOVER_DIR = PROJECT_DIR / "flyover"
SHOTS_DIR = FLYOVER_DIR / "shots"

C_CURR = "#2dd4bf"
C_CULV = "#38bdf8"
C_VAL = "#7dd3fc"
C_CANAL = "#0ea5e9"
C_AQUED = "#f59e0b"
C_FORMER = "#818cf8"
C_FLOOD = "#fb7185"

TOKYO_BBOX = (139.55, 35.53, 139.93, 35.82)
SHIBUYA_BBOX = (139.692, 35.652, 139.710, 35.667)
GINZA_BBOX = (139.756, 35.660, 139.778, 35.678)
NIHONBASHI_BBOX = (139.766, 35.676, 139.792, 35.696)
ASAKUSA_BBOX = (139.782, 35.698, 139.812, 35.726)
SHITAMACHI_BBOX = (139.77, 35.67, 139.87, 35.74)
YAMANOTE_BBOX = (139.58, 35.59, 139.76, 35.79)
ARAKAWA_BBOX = (139.74, 35.72, 139.90, 35.82)
TAMAGAWA_BBOX = (139.60, 35.53, 139.78, 35.62)


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
    fill_opacity: float = 0.55,
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


def ui_header(
    tag: str,
    counter_val: float | str,
    counter_from: float | None = None,
    caption: str = "復活した川（累計）",
    unit: str = "km",
) -> list[dict]:
    c: dict = {
        "type": "counter",
        "screen": [1460, 110],
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


def line(
    voice: str,
    text: str,
    *,
    speech: str | None = None,
    face: str = "normal",
    react: str = "normal",
) -> dict:
    item: dict = {"voice": voice, "text": text, "face": face, "react": react}
    if speech is not None:
        item["speech"] = speech
    return item


def chapter_envelope(
    shots: list[dict],
    *,
    plateau_area: str | None = None,
    opacity_keyframes: list | float | None = None,
    exaggeration: float = 1.6,
    hillshade: float = 0.3,
) -> dict:
    doc: dict = {
        "width": 1920,
        "height": 1080,
        "fps": 24,
        "base": "seamlessphoto",
        "world": False,
        "dem": "gsi",
        "exaggeration": exaggeration,
        "hillshade": hillshade,
        "saturation": -0.12,
        "contrast": 0.06,
        "voices": {
            "a": {"speaker": 3, "name": "ずんだもん", "speed": 1.28, "color": "#ffe94a"},
            "b": {"speaker": 2, "name": "四国めたん", "speed": 1.2, "color": "#ff9ca7"},
        },
        "tts": {
            "url": "http://127.0.0.1:50021",
            "padStart": 0.3,
            "pause": 0.25,
            "padEnd": 0.45,
            "wrap": 24,
        },
        "reaction": {
            "characters": {
                "a": {"sprites": "assets/chara/zundamon", "seed": "zundamon"},
                "b": {"sprites": "assets/chara/metan", "seed": "metan"},
            },
            "order": ["b", "a"],
            "height": 240,
            "side": "right",
            "bottom": 150,
        },
        "credits": [
            "水路再現：オープンデータによる再現イメージ（位置は概略）",
            "出典：国土交通省 PLATEAU・国土数値情報 / 国土地理院 / OpenStreetMap contributors (ODbL-1.0) / 東京都浸水実績図 (CC BY 4.0)",
        ],
        "shots": shots,
    }
    if plateau_area is not None:
        pb: dict = {
            "manifest": f"assets/buildings-3d/{plateau_area}/manifest.json",
            "heightOffset": -39,
            "workers": 3,
        }
        if opacity_keyframes is not None:
            pb["opacity"] = opacity_keyframes
        doc["plateauBuildings"] = [pb]
    return doc


def build_ch00_intro(data: dict) -> dict:
    f01, f02 = data["f01"], data["f02"]
    shots = [
        {
            "from": {"center": [139.6994, 35.6604], "zoom": 16.5, "pitch": 66, "bearing": 35},
            "to": {"center": [139.7016, 35.6584], "zoom": 15.6, "pitch": 54, "bearing": 5},
            "lines": [
                line("a", "ここ、渋谷のセンター街なのだ！ビルがぎっしりなのだ。", face="point"),
                line("b", "でも、ビルを透かして足元を見てみましょう。", face="smile", react="surprise"),
                line("a", "うわっ！ビルの真下に青い川が出てきたのだ！？", face="surprise", react="smile"),
                line("b", "今は暗渠になった「渋谷川」と「宇田川」の合流点よ。", speech="いまはあんきょになった、しぶやがわと、うだがわのごうりゅうてんよ。", face="point", react="surprise"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, SHIBUYA_BBOX, 15), C_CURR, 5)
                + to_line_overlays(select_features(f02, SHIBUYA_BBOX, 35), C_CULV, 8, draw=[0.35, 0.85], show=[0.35, 1])
                + [
                    {"type": "label", "screen": tag_screen("OP｜渋谷センター街の足元に眠る川"), "text": "OP｜渋谷センター街の足元に眠る川", "style": "tag"},
                    {"type": "label", "at": [139.7016, 35.6580], "text": "渋谷川（暗渠）", "dot": True, "show": [0.45, 1]},
                    {"type": "label", "at": [139.6986, 35.6618], "text": "宇田川（暗渠）", "dot": True, "show": [0.45, 1]},
                    {"type": "panel", "src": "assets/photos/shibuya_cat_street.jpg", "caption": "旧渋谷川上の遊歩道（キャットストリート）", "credit": "写真：Harani0403 / Wikimedia Commons（CC0）", "screen": [60, 120], "width": 440, "show": [0.55, 1]},
                    {"type": "note", "text": "3D建物：PLATEAU + 地理院・OSM補完（推定テクスチャ含む）"},
                ]
            ),
        },
        {
            "path": "fly",
            "from": {"center": [139.7016, 35.6580], "zoom": 14.2, "pitch": 46, "bearing": 0},
            "to": {"center": [139.74, 35.68], "zoom": 10.6, "pitch": 30, "bearing": 0},
            "lines": [
                line("a", "東京には、こういう消えた川が他にもあるのか？", speech="とうきょうには、こういうきえたかわがほかにもあるのか？", face="trouble"),
                line("b", "23区全体を見ると、いま見えている開渠の川は 369.79 km。", speech="にじゅうさんくぜんたいをみると、いまみえているかいきょのかわは、さんびゃくろくじゅうきゅうてんななきゅうキロメートル。", face="normal", react="normal"),
                line("a", "それだけでも結構ある気がするのだ。", face="normal", react="normal"),
                line("b", "ところが、戦後の開発で暗渠や埋立地になった川が、まだ何百キロも隠れているのよ。", speech="ところが、せんごのかいはつであんきょやうめたてちになったかわが、まだなんびゃくキロもかくれているのよ。", face="point", react="surprise"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, TOKYO_BBOX, 100, min_len_m=400), C_CURR, 3)
                + ui_header("OP｜23区で「いま見えている川」は 369.79 km", 369.79, caption="現行開渠河川")
            ),
        },
        {
            "from": {"center": [139.72, 35.67], "zoom": 10.8, "pitch": 34, "bearing": -6},
            "to": {"center": [139.76, 35.69], "zoom": 10.7, "pitch": 30, "bearing": 4},
            "lines": [
                line("b", "今回は商用利用もできるオープンデータだけを使って、4種類の失われた川を地図に重ねていくわ。", speech="こんかいはしょうようりようもできるオープンデータだけをつかって、よんしゅるいのうしなわれたかわをちずにかさねていくわ。", face="normal"),
                line("a", "暗渠・掘割・上水・旧河道の4つを、消さずに全部積み上げるのだな！", speech="あんきょ、ほりわり、じょうすい、きゅうかどうのよっつを、けさずにぜんぶつみあげるのだな！", face="smile", react="smile"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, TOKYO_BBOX, 100, min_len_m=400), C_CURR, 3)
                + [
                    {"type": "label", "screen": tag_screen("OP｜オープンデータだけで東京の川を4段階復元"), "text": "OP｜オープンデータだけで東京の川を4段階復元", "style": "tag"},
                    {"type": "quote", "source": "使用データ方針", "text": "国土地理院・OSM・国土数値情報・東京都浸水実績図など商用利用可能なデータのみ使用", "marks": False, "screen": [70, 140], "width": 740},
                ]
            ),
        },
    ]
    return chapter_envelope(shots, plateau_area="shibuya", opacity_keyframes=[[0, 1.0], [3.5, 1.0], [6.0, 0.35], [20, 0.35]], exaggeration=1.0, hillshade=0.2)


def build_ch01_yamanote(data: dict) -> dict:
    f01, f02 = data["f01"], data["f02"]
    shots = [
        {
            "from": {"center": [139.63, 35.63], "zoom": 13.0, "pitch": 58, "bearing": 40},
            "to": {"center": [139.67, 35.66], "zoom": 11.7, "pitch": 48, "bearing": 15},
            "lines": [
                line("b", "第1章は、世田谷や目黒などの「山の手」の台地からスタートよ。", speech="だいいっしょうは、せたがややめぐろなどの、やまのてのだいちからスタートよ。", face="point"),
                line("a", "一見ふつうの住宅街だけど、標高を少し強調すると細かい谷だらけなのだ！", face="surprise", react="normal"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, YAMANOTE_BBOX, 40, min_len_m=300), C_CURR, 2)
                + ui_header("第1章｜住宅街の下に刻まれた無数の「谷」", 0.0, caption="復活した川（累計）")
                + [{"type": "label", "at": [139.64, 35.64], "text": "目黒川が削った谷筋", "dot": True}]
            ),
        },
        {
            "from": {"center": [139.64, 35.64], "zoom": 12.2, "pitch": 45, "bearing": 10},
            "to": {"center": [139.67, 35.67], "zoom": 11.4, "pitch": 36, "bearing": 0},
            "lines": [
                line("b", "ここにOSMの暗渠データと、標高モデルから抽出した谷筋を一気に重ねるわ。", speech="ここにオーエスエムのあんきょデータと、ひょうこうモデルからちゅうしゅつしたたにすじをいっきにかさねるわ。", face="normal"),
                line("a", "すごい数なのだ！一気に 384.31 km も増えたのだ！", speech="すごいかずなのだ！いっきにさんびゃくはちじゅうよんてんさんいちキロメートルもふえたのだ！", face="surprise", react="smile"),
                line("b", "さっきの「いま見えている川」369.79 km を、暗渠と谷筋だけで上回ってしまったのよ。", speech="さっきの、いまみえているかわ、さんびゃくろくじゅうきゅうてんななきゅうキロメートルを、あんきょとたにすじだけでうわまわってしまったのよ。", face="point", react="surprise"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, YAMANOTE_BBOX, 40, min_len_m=300), C_CURR, 2)
                + to_line_overlays(select_features(f02, YAMANOTE_BBOX, 80, min_len_m=600, category="culvert_osm"), C_CULV, 4, draw=[0.1, 0.75])
                + to_line_overlays(select_features(f02, YAMANOTE_BBOX, 60, min_len_m=800, category="valley_dem"), C_VAL, 2, draw=[0.2, 0.85])
                + ui_header("第1章｜暗渠と谷筋だけで +384.31 km", 384.31, counter_from=0.0)
            ),
        },
        {
            "from": {"center": [139.69, 35.63], "zoom": 12.8, "pitch": 42, "bearing": -25},
            "to": {"center": [139.65, 35.65], "zoom": 12.2, "pitch": 35, "bearing": -10},
            "lines": [
                line("b", "水系ごとに見ると、目黒川水系は開渠が 11.66 km なのに、暗渠・谷筋は 87.94 km もあるわ。", speech="すいけいごとにみると、めぐろがわすいけいはかいきょがじゅういってんろくろくキロメートルなのに、あんきょ・たにすじははちじゅうななてんきゅうよんキロメートルもあるわ。", face="point"),
                line("a", "目黒川のほとんどは、見えない支流や谷が集まってできていたのだな。", face="trouble", react="normal"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, YAMANOTE_BBOX, 30, min_len_m=300), C_CURR, 2)
                + to_line_overlays(select_features(f02, YAMANOTE_BBOX, 60, min_len_m=700), C_CULV, 4)
                + [
                    {"type": "label", "screen": tag_screen("第1章｜目黒川水系は 87.94 km が暗渠・谷筋"), "text": "第1章｜目黒川水系は 87.94 km が暗渠・谷筋", "style": "tag"},
                    {"type": "panel", "src": "assets/fig2_basin_comparison.png", "caption": "主要水系別：現行開渠 vs 暗渠・谷筋", "credit": "集計：basin_comparison.csv", "screen": [1080, 120], "width": 760},
                ]
            ),
        },
        {
            "from": {"center": [139.662, 35.656], "zoom": 16.0, "pitch": 35, "bearing": 20},
            "to": {"center": [139.670, 35.661], "zoom": 15.2, "pitch": 20, "bearing": 0},
            "lines": [
                line("a", "代沢の北沢川緑道みたいに、今はきれいな遊歩道になっている場所も多いのだ。", speech="だいざわのきたざわがわりょくどうみたいに、いまはきれいなゆうほどうになっているばしょもおおいのだ。", face="smile"),
                line("b", "背景を1945年の空中写真に切り替えると、ほら、暗渠になる前の川筋がくっきり見えるわ。", speech="はいけいをせんきゅうひゃくよんじゅうごねんのくうちゅうしゃしんにきりかえると、ほら、あんきょになるまえのかわすじがくっきりみえるわ。", face="point", react="surprise"),
                line("a", "次はもっと驚く、都心のビルや高速道路の下をめぐるのだ！", face="point", react="smile"),
            ],
            "overlays": (
                [{"type": "base", "layer": "ort_USA10", "show": [0.4, 1], "fade": 0.25}]
                + to_line_overlays(select_features(f02, (139.65, 35.645, 139.685, 35.675), 30), C_CULV, 4)
                + [
                    {"type": "label", "screen": tag_screen("第1章｜緑道の下→1945年空中写真で確認"), "text": "第1章｜緑道の下→1945年空中写真で確認", "style": "tag"},
                    {"type": "label", "at": [139.668, 35.660], "text": "北沢川（暗渠化前）", "dot": True},
                    {"type": "panel", "src": "assets/photos/kitazawa_greenway_daizawa.jpg", "caption": "現在の北沢川緑道（世田谷区代沢）", "credit": "写真：Shiragiku / Wikimedia Commons（CC BY 2.5）", "screen": [60, 130], "width": 420, "show": [0, 0.5]},
                    {"type": "note", "text": "1945〜50年 米軍撮影空中写真（国土地理院）／地名は現代のもの"},
                ]
            ),
        },
    ]
    return chapter_envelope(shots, exaggeration=1.8, hillshade=0.35)


def build_ch02a_ginza(data: dict) -> dict:
    f01, f03 = data["f01"], data["f03"]
    shots = [
        {
            "from": {"center": [139.7652, 35.6682], "zoom": 16.5, "pitch": 64, "bearing": 28},
            "to": {"center": [139.7685, 35.6725], "zoom": 16.0, "pitch": 58, "bearing": 28},
            "lines": [
                line("b", "第2章は都心の「消えた川めぐり」。まずは銀座・新橋・築地エリアよ。", speech="だいにしょうはとしんの、きえたかわめぐり。まずはぎんざ、しんばし、つきじエリアよ。", face="point"),
                line("a", "東銀座のビルが並んでいるけれど、昭和通りの1本西側が怪しいのだ…", face="trouble"),
                line("b", "建物を透かすと現れるのが、かつて江戸の水運を支えた「三十間堀」よ。", speech="たてものをすかすとあらわれるのが、かつてえどのすいうんをささえた、さんじっけんぼりよ。", face="smile", react="surprise"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, GINZA_BBOX, 20), C_CURR, 3)
                + to_poly_overlays(select_features(f03, GINZA_BBOX, 45), C_CANAL, 0.7, "#ffffff", 3, show=[0.4, 1])
                + [
                    {"type": "label", "screen": tag_screen("第2章①｜銀座のど真ん中を貫いていた三十間堀"), "text": "第2章①｜銀座のど真ん中を貫いていた三十間堀", "style": "tag"},
                    {"type": "label", "at": [139.7670, 35.6700], "text": "三十間堀", "dot": True, "show": [0.45, 1]},
                    {"type": "note", "text": "3D建物：PLATEAU + 地理院・OSM補完（推定テクスチャ含む）"},
                ]
            ),
        },
        {
            "from": {"center": [139.7635, 35.6685], "zoom": 16.2, "pitch": 58, "bearing": 45},
            "to": {"center": [139.7685, 35.6695], "zoom": 15.3, "pitch": 48, "bearing": -10},
            "lines": [
                line("a", "あっ！銀座をぐるっと囲む東京高速道路、いわゆるKK線の下も全部川だったのか！？", speech="あっ！ぎんざをぐるっとかこむとうきょうこうそくどうろ、いわゆるケーケーせんのしたもぜんぶかわだったのか！？", face="surprise"),
                line("b", "そう。外濠川・京橋川・汐留川というお堀を埋め立てて造られた高架道路なの。", speech="そう。そとぼりがわ、きょうばしがわ、しおどめがわというおほりをうめたててつくられたこうかどうろなの。", face="point", react="surprise"),
                line("b", "東側の築地川も、今は首都高都心環状線 C1 の掘り割りと公園になっているわ。", speech="ひがしがわのつきじがわも、いまはしゅとこうとしんかんじょうせんシーワンのほりわりとこうえんになっているわ。", face="normal", react="normal"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, GINZA_BBOX, 20), C_CURR, 3)
                + to_poly_overlays(select_features(f03, GINZA_BBOX, 45), C_CANAL, 0.7, "#ffffff", 3)
                + ui_header("第2章①｜KK線・首都高C1の真下に蘇る掘割網", 404.44, counter_from=384.31)
                + [
                    {"type": "label", "at": [139.7630, 35.6710], "text": "外濠川・京橋川", "dot": True},
                    {"type": "label", "at": [139.7720, 35.6670], "text": "築地川（首都高C1下）", "dot": True},
                    {"type": "panel", "src": "assets/photos/tokyo_expressway_higashi_ginza.jpg", "caption": "東京高速道路（KK線・東銀座付近）", "credit": "写真：Ebiebi2 / Wikimedia Commons（CC0）", "screen": [55, 120], "width": 400, "show": [0.05, 0.52]},
                    {"type": "panel", "src": "assets/photos/tsukiji_river_park.jpg", "caption": "築地川公園（旧築地川跡）", "credit": "写真：ja:User:築地川 / Wikimedia Commons（CC BY 4.0）", "screen": [55, 120], "width": 400, "show": [0.52, 1]},
                    {"type": "note", "text": "3D建物：PLATEAU + 地理院・OSM補完（推定テクスチャ含む）"},
                ]
            ),
        },
    ]
    return chapter_envelope(shots, plateau_area="ginza", opacity_keyframes=[[0, 1.0], [4.5, 1.0], [7.0, 0.36], [40, 0.36]], exaggeration=1.0, hillshade=0.2)


def build_ch02b_nihonbashi(data: dict) -> dict:
    f01, f03 = data["f01"], data["f03"]
    shots = [
        {
            "from": {"center": [139.7795, 35.6865], "zoom": 16.3, "pitch": 58, "bearing": 165},
            "to": {"center": [139.7785, 35.6835], "zoom": 15.8, "pitch": 50, "bearing": 175},
            "lines": [
                line("b", "続いては日本橋・人形町エリア。オフィスビルの足元に注目よ。", face="point"),
                line("a", "うわ、街の真ん中に2本ならんで水路が突き刺さっているのだ！", face="surprise"),
                line("b", "江戸の問屋街へ荷物を運んだ「東堀留川」と「西堀留川」よ。", speech="えどのとんやがいへにもつをはこんだ、ひがしほりどめがわと、にしほりどめがわよ。", face="normal", react="normal"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, NIHONBASHI_BBOX, 20), C_CURR, 3)
                + to_poly_overlays(select_features(f03, NIHONBASHI_BBOX, 55), C_CANAL, 0.72, "#ffffff", 3, show=[0.35, 1])
                + [
                    {"type": "label", "screen": tag_screen("第2章②｜人形町に刺さる「2本の入堀」"), "text": "第2章②｜人形町に刺さる「2本の入堀」", "style": "tag"},
                    {"type": "label", "at": [139.7806, 35.6852], "text": "東堀留川", "dot": True, "show": [0.45, 1]},
                    {"type": "label", "at": [139.7776, 35.6832], "text": "西堀留川", "dot": True, "show": [0.45, 1]},
                    {"type": "note", "text": "3D建物：PLATEAU + 地理院・OSM補完（推定テクスチャ含む）"},
                ]
            ),
        },
        {
            "from": {"center": [139.7765, 35.6820], "zoom": 16.2, "pitch": 62, "bearing": 195},
            "to": {"center": [139.7745, 35.6780], "zoom": 15.6, "pitch": 52, "bearing": 185},
            "lines": [
                line("a", "この江戸橋ジャンクションの真下にも太い川があるのだ！", speech="このえどばしジャンクションのましたにもふといかわがあるのだ！", face="point"),
                line("b", "日本橋川と京橋川をつないでいた「楓川」ね。戦後の1945年空中写真にも本物の水面が写っているわ。", speech="にほんばしがわときょうばしがわをつないでいた、かえでがわね。せんごのせんきゅうひゃくよんじゅうごねんくうちゅうしゃしんにもほんもののすいめんがうつっているわ。", face="smile", react="surprise"),
            ],
            "overlays": (
                [{"type": "base", "layer": "ort_USA10", "show": [0.48, 1], "fade": 0.25}]
                + to_line_overlays(select_features(f01, NIHONBASHI_BBOX, 20), C_CURR, 3)
                + to_poly_overlays(select_features(f03, NIHONBASHI_BBOX, 55), C_CANAL, 0.6, "#ffffff", 3)
                + [
                    {"type": "label", "screen": tag_screen("第2章②｜江戸橋JCTの下の「楓川」と1945年写真"), "text": "第2章②｜江戸橋JCTの下の「楓川」と1945年写真", "style": "tag"},
                    {"type": "label", "at": [139.7760, 35.6800], "text": "楓川", "dot": True},
                    {"type": "note", "text": "1945〜50年 米軍撮影空中写真（国土地理院）／3D建物は現在位置の参考"},
                ]
            ),
        },
        {
            "from": {"center": [139.7755, 35.6895], "zoom": 15.8, "pitch": 50, "bearing": 85},
            "to": {"center": [139.7845, 35.6880], "zoom": 15.3, "pitch": 46, "bearing": 70},
            "lines": [
                line("b", "さらに北側の神田との区境には「龍閑川」、東へ抜けると「浜町川」と緑道が続いていたの。", speech="さらにきたがわのかんだとのくざかいには、りゅうかんがわ、ひがしへぬけると、はまちょうがわとりょくどうがつづいていたの。", face="normal"),
                line("a", "今の緑道や区の境界線が、昔の川の形そのものなのだな！", speech="いまのりょくどうや、くのきょうかいせんが、むかしのかわのかたちそのものなのだな！", face="smile", react="smile"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, NIHONBASHI_BBOX, 20), C_CURR, 3)
                + to_poly_overlays(select_features(f03, NIHONBASHI_BBOX, 55), C_CANAL, 0.7, "#ffffff", 3)
                + [
                    {"type": "label", "screen": tag_screen("第2章②｜龍閑川〜浜町川・隅田川への連絡路"), "text": "第2章②｜龍閑川〜浜町川・隅田川への連絡路", "style": "tag"},
                    {"type": "label", "at": [139.7785, 35.6904], "text": "龍閑川", "dot": True},
                    {"type": "label", "at": [139.7845, 35.6890], "text": "浜町川", "dot": True},
                    {"type": "panel", "src": "assets/photos/hamachogawa_greenway.jpg", "caption": "浜町川緑道（中央区日本橋浜町）", "credit": "写真：ja:User:築地川 / Wikimedia Commons（CC0）", "screen": [55, 120], "width": 400},
                    {"type": "note", "text": "3D建物：PLATEAU + 地理院・OSM補完（推定テクスチャ含む）"},
                ]
            ),
        },
    ]
    return chapter_envelope(shots, plateau_area="nihonbashi", opacity_keyframes=[[0, 1.0], [2.5, 1.0], [5.0, 0.36], [60, 0.36]], exaggeration=1.0, hillshade=0.2)


def build_ch02c_asakusa(data: dict) -> dict:
    f01, f03 = data["f01"], data["f03"]
    shots = [
        {
            "from": {"center": [139.7975, 35.7215], "zoom": 16.2, "pitch": 62, "bearing": 125},
            "to": {"center": [139.8045, 35.7165], "zoom": 15.6, "pitch": 54, "bearing": 115},
            "lines": [
                line("b", "都心めぐりの最後は、浅草・台東・下町エリアよ。", face="point"),
                line("a", "浅草寺の北側を、隅田川に向かってまっすぐ伸びる水路があるのだ！", speech="せんそうじのきたがわを、すみだがわにむかってまっすぐのびるすいろがあるのだ！", face="surprise"),
                line("b", "これが吉原へ舟で通った「山谷堀」。広重の浮世絵にも描かれた名所だったのよ。", speech="これがよしわらへふねでかよった、さんやぼり。ひろしげのうきよえにもえがかれためいしょだったのよ。", face="smile", react="smile"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, ASAKUSA_BBOX, 20), C_CURR, 3)
                + to_poly_overlays(select_features(f03, ASAKUSA_BBOX, 55), C_CANAL, 0.72, "#ffffff", 3, show=[0.25, 1])
                + [
                    {"type": "label", "screen": tag_screen("第2章③｜浅草・山谷堀（吉原〜隅田川）"), "text": "第2章③｜浅草・山谷堀（吉原〜隅田川）", "style": "tag"},
                    {"type": "label", "at": [139.8020, 35.7180], "text": "山谷堀", "dot": True},
                    {"type": "panel", "src": "assets/photos/sanyabori_ukiyoe_cropped.jpg", "caption": "名所江戸百景「真乳山山谷堀夜景」", "credit": "図版：広重 / Wikimedia Commons（Public domain）", "screen": [55, 115], "width": 310},
                    {"type": "note", "text": "3D建物：PLATEAU + 地理院・OSM補完（推定テクスチャ含む）"},
                ]
            ),
        },
        {
            "from": {"center": [139.7860, 35.7025], "zoom": 16.0, "pitch": 54, "bearing": 10},
            "to": {"center": [139.818, 35.694], "zoom": 13.4, "pitch": 40, "bearing": 15},
            "lines": [
                line("b", "新堀通りの「三味線堀」や、隅田川を渡った深川の大横川・竪川なども親水公園として形を残しているわ。", speech="しんぼりどおりの、しゃみせんぼりや、すみだがわをわたったふかがわのおおよこがわ、たてかわなども、しんすいこうえんとしてかたちをのこしているわ。", face="normal"),
                line("a", "都心の埋立掘割だけでも 81 件、およそ 20 km 分が街の下に隠れていたのだな！", speech="としんのうめたてほりわりだけでも、はちじゅういっけん、およそにじゅっキロメートルぶんがまちのしたにかくれていたのだな！", face="point", react="smile"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, SHITAMACHI_BBOX, 40), C_CURR, 2)
                + to_poly_overlays(select_features(f03, SHITAMACHI_BBOX, 55), C_CANAL, 0.65, "#ffffff", 2)
                + ui_header("第2章③｜三味線堀〜深川の大横川・竪川親水公園", 404.44)
                + [
                    {"type": "label", "at": [139.7865, 35.7045], "text": "三味線堀", "dot": True},
                    {"type": "label", "at": [139.814, 35.704], "text": "大横川親水公園", "dot": True, "show": [0.4, 1]},
                    {"type": "label", "at": [139.825, 35.693], "text": "竪川河川敷公園", "dot": True, "show": [0.45, 1]},
                ]
            ),
        },
    ]
    return chapter_envelope(shots, plateau_area="asakusa", opacity_keyframes=[[0, 1.0], [2.5, 1.0], [5.0, 0.36], [40, 0.36]], exaggeration=1.0, hillshade=0.2)


def build_ch03_aqueducts(data: dict) -> dict:
    f01, f02, f03, f04 = data["f01"], data["f02"], data["f03"], data["f04"]
    shots = [
        {
            "from": {"center": [139.615, 35.684], "zoom": 13.6, "pitch": 55, "bearing": 95},
            "to": {"center": [139.675, 35.676], "zoom": 12.6, "pitch": 46, "bearing": 35},
            "lines": [
                line("b", "第3章は、自然の川とはまったく逆の場所を走る「旧上水」よ。", speech="だいさんしょうは、しぜんのかわとはまったくぎゃくのばしょをはしる、きゅうじょうすいよ。", face="point"),
                line("a", "あれっ？水色の谷筋のあいだの、高い尾根の上をオレンジ色の線が突っ走っているのだ！", speech="あれっ？みずいろのたにすじのあいだの、たかいおねのうえを、オレンジいろのせんがつっぱしっているのだ！", face="surprise"),
                line("b", "これが「玉川上水」。自然の重力だけで江戸へ水を届けるため、分水嶺の尾根を選んで掘られたのよ。", speech="これがたまがわじょうすい。しぜんのじゅうりょくだけでえどへみずをとどけるため、ぶんすいれいのおねをえらんでほられたのよ。", face="smile", react="surprise"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, YAMANOTE_BBOX, 30, min_len_m=300), C_CURR, 2)
                + to_line_overlays(select_features(f02, YAMANOTE_BBOX, 50, min_len_m=700), C_CULV, 2)
                + to_line_overlays(select_features(f04, TOKYO_BBOX, 64), C_AQUED, 5, draw=[0.1, 0.85])
                + ui_header("第3章｜谷の逆！尾根の上を走る玉川上水", 459.54, counter_from=404.44)
                + [
                    {"type": "label", "at": [139.645, 35.676], "text": "玉川上水（尾根ルート）", "dot": True},
                    {"type": "panel", "src": "assets/photos/tamagawa_josui_greenway.jpg", "caption": "玉川上水第二緑道（旧玉川上水）", "credit": "写真：多摩に暇人 / Wikimedia Commons（CC BY 3.0）", "screen": [55, 130], "width": 410},
                ]
            ),
        },
        {
            "from": {"center": [139.675, 35.676], "zoom": 12.4, "pitch": 42, "bearing": 20},
            "to": {"center": [139.70, 35.66], "zoom": 11.1, "pitch": 34, "bearing": 0},
            "lines": [
                line("b", "千川上水や六郷用水なども加えると、旧上水だけで 55.10 km。", speech="せんかわじょうすいやろくごうようすいなどもくわえると、きゅうじょうすいだけで、ごじゅうごてんいちれいキロメートル。", face="normal"),
                line("a", "これでライン状の失われた川は、合計 459.54 km になったのだ！", speech="これでラインじょうの、うしなわれたかわは、ごうけいよんひゃくごじゅうきゅうてんごよんキロメートルになったのだ！", face="point", react="smile"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, TOKYO_BBOX, 50, min_len_m=500), C_CURR, 2)
                + to_line_overlays(select_features(f02, TOKYO_BBOX, 60, min_len_m=800), C_CULV, 2)
                + to_poly_overlays(select_features(f03, TOKYO_BBOX, 40), C_CANAL, 0.5, "#ffffff", 1)
                + to_line_overlays(select_features(f04, TOKYO_BBOX, 64), C_AQUED, 4)
                + ui_header("第3章｜千川上水・六郷用水も合流（計 459.54 km）", 459.54)
            ),
        },
    ]
    return chapter_envelope(shots, exaggeration=1.7, hillshade=0.35)


def build_ch04_former_channels(data: dict) -> dict:
    f01, f04, f05 = data["f01"], data["f04"], data["f05"]
    shots = [
        {
            "from": {"center": [139.785, 35.755], "zoom": 13.4, "pitch": 52, "bearing": -20},
            "to": {"center": [139.815, 35.775], "zoom": 12.1, "pitch": 40, "bearing": 0},
            "lines": [
                line("b", "第4章は、川の形がもっとダイナミックに変わる「旧河道」よ。", speech="だいよんしょうは、かわのかたちがもっとダイナミックにかわる、きゅうかどうよ。", face="point"),
                line("a", "まっすぐな荒川のすぐ横に、うねうね曲がった紫の跡がたくさん浮かび上がったのだ！", face="surprise"),
                line("b", "今の荒川は明治・大正の放水路でまっすぐになったけれど、昔は低地を自由に蛇行する暴れ川だったの。", speech="いまのあらかわはめいじ、たいしょうのほうすいろでまっすぐになったけれど、むかしはていちをじゆうにだこうするあばれがわだったの。", face="normal", react="normal"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, ARAKAWA_BBOX, 40), C_CURR, 2)
                + to_poly_overlays(select_features(f05, ARAKAWA_BBOX, 80), C_FORMER, 0.6, "#c7d2fe", 2, show=[0.25, 1])
                + ui_header("第4章｜真っ直ぐな荒川の横に眠る巨大な蛇行跡", 5.84, caption="旧河道（治水地形分類図）", unit="km²")
                + [{"type": "label", "at": [139.805, 35.785], "text": "旧河道（暴れ川の跡）", "dot": True, "show": [0.35, 1]}]
            ),
        },
        {
            "path": "fly",
            "from": {"center": [139.70, 35.565], "zoom": 13.2, "pitch": 45, "bearing": 20},
            "to": {"center": [139.74, 35.675], "zoom": 10.7, "pitch": 32, "bearing": 0},
            "lines": [
                line("b", "多摩川の旧河道も含めると、合計 5.837 平方キロメートル。これで全5層の「消えた川」がすべて揃ったわ。", speech="たまがわのきゅうかどうもふくめると、ごうけい、ごてん、はちさんなな、へいほうキロメートル。これでぜんごそうの、きえたかわがすべてそろったわ。", face="smile"),
                line("a", "すごい密度なのだ！でも、これを知っていると何か役に立つのか？", face="trouble", react="point"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, TOKYO_BBOX, 40, min_len_m=500), C_CURR, 2)
                + to_line_overlays(select_features(f04, TOKYO_BBOX, 40), C_AQUED, 3)
                + to_poly_overlays(select_features(f05, TOKYO_BBOX, 60), C_FORMER, 0.55, "#c7d2fe", 2)
                + ui_header("第4章｜多摩川旧河道も加わり全5層が出揃う", 459.54)
            ),
        },
    ]
    return chapter_envelope(shots, exaggeration=1.5, hillshade=0.3)


def build_ch05_ending(data: dict) -> dict:
    f01, f02, f03, f04, f05, f06 = data["f01"], data["f02"], data["f03"], data["f04"], data["f05"], data["f06"]
    shots = [
        {
            "from": {"center": [139.72, 35.67], "zoom": 11.2, "pitch": 36, "bearing": -10},
            "to": {"center": [139.74, 35.68], "zoom": 10.6, "pitch": 30, "bearing": 0},
            "lines": [
                line("b", "最後に、1974年から2019年までの「東京都 浸水実績図」を赤いポリゴンで重ねてみましょう。", speech="さいごに、せんきゅうひゃくななじゅうよねんからにせんじゅうきゅうねんまでの、とうきょうとしんすいじっせきずを、あかいポリゴンでかさねてみましょう。", face="point"),
                line("a", "うわっ…！さっきまで辿ってきた昔の川と、赤い浸水エリアがぴったり重なっているのだ！", face="surprise"),
                line("b", "23区内の浸水実績 4,759 件のうち、およそ 45.2% が、失われた川の 100 メートル以内に集中していたのよ。", speech="にじゅうさんくないのしんすいじっせき、よんせんななひゃくごじゅうきゅうけんのうち、およそよんじゅうごてんにパーセントが、うしなわれたかわのひゃくメートルいないにしゅうちゅうしていたのよ。", face="sad", react="sad"),
            ],
            "overlays": (
                to_line_overlays(select_features(f02, TOKYO_BBOX, 50, min_len_m=900), C_CULV, 2)
                + to_poly_overlays(select_features(f03, TOKYO_BBOX, 30), C_CANAL, 0.4, "#ffffff", 1)
                + to_poly_overlays(select_features(f05, TOKYO_BBOX, 40), C_FORMER, 0.4, "#c7d2fe", 1)
                + to_poly_overlays(select_features(f06, TOKYO_BBOX, 60), C_FLOOD, 0.55, "#fda4af", 1, show=[0.2, 1])
                + [
                    {"type": "label", "screen": tag_screen("終章｜浸水実績の 45.2% が元・川の100m以内"), "text": "終章｜浸水実績の 45.2% が元・川の100m以内", "style": "tag"},
                    {"type": "panel", "src": "assets/fig3_flood_overlap_validation.png", "caption": "浸水実績ポリゴンとの最短距離分布", "credit": "東京都浸水実績図（1974〜2019年）", "screen": [1080, 120], "width": 760},
                ]
            ),
        },
        {
            "from": {"center": [139.74, 35.68], "zoom": 10.8, "pitch": 38, "bearing": -10},
            "to": {"center": [139.74, 35.68], "zoom": 10.3, "pitch": 28, "bearing": 12},
            "lines": [
                line("b", "川は埋め立てられて姿を変えても、土地の低さや水の通り道としての記憶は消えないのね。", speech="かわはうめたてられてすがたをかえても、とちのひくさやみずのとおりみちとしてのきおくはきえないのね。", face="normal"),
                line("a", "いつもの商店街や高速道路の下にも、昔の川が眠っているかもしれないのだ。みんなも探してみてほしいのだ！", face="smile", react="smile"),
            ],
            "overlays": (
                to_line_overlays(select_features(f01, TOKYO_BBOX, 45, min_len_m=500), C_CURR, 2)
                + to_line_overlays(select_features(f02, TOKYO_BBOX, 65, min_len_m=800), C_CULV, 2)
                + to_poly_overlays(select_features(f03, TOKYO_BBOX, 45), C_CANAL, 0.55, "#ffffff", 1)
                + to_line_overlays(select_features(f04, TOKYO_BBOX, 50), C_AQUED, 3)
                + to_poly_overlays(select_features(f05, TOKYO_BBOX, 50), C_FORMER, 0.5, "#c7d2fe", 1)
                + ui_header("終章｜すべてを重ねた「本来の東京」", 459.54, caption="復活した川（累計ライン）")
                + [{"type": "note", "text": "全5層統合（復元ライン459.54km + 面6.83km²）※再現イメージ"}]
            ),
        },
    ]
    return chapter_envelope(shots, exaggeration=1.6, hillshade=0.3)


def main() -> None:
    data = {
        "f01": load_geojson("01_current_rivers.geojson"),
        "f02": load_geojson("02_culvert_and_valleys.geojson"),
        "f03": load_geojson("03_filled_canals.geojson"),
        "f04": load_geojson("04_old_aqueducts.geojson"),
        "f05": load_geojson("05_former_channels.geojson"),
        "f06": load_geojson("06_flood_overlap.geojson"),
    }

    chapters = [
        ("ch00-intro", "導入｜いまは見えない東京の川", build_ch00_intro(data)),
        ("ch01-yamanote", "第1章｜山の手の暗渠と谷筋", build_ch01_yamanote(data)),
        ("ch02a-ginza", "第2章①｜銀座・汐留・築地の掘割", build_ch02a_ginza(data)),
        ("ch02b-nihonbashi", "第2章②｜日本橋・神田の入堀", build_ch02b_nihonbashi(data)),
        ("ch02c-asakusa", "第2章③｜浅草・下町の堀と親水公園", build_ch02c_asakusa(data)),
        ("ch03-aqueducts", "第3章｜尾根を走る旧上水", build_ch03_aqueducts(data)),
        ("ch04-former-channels", "第4章｜荒川・多摩川の旧河道", build_ch04_former_channels(data)),
        ("ch05-ending", "終章｜すべてを重ねた東京と浸水実績", build_ch05_ending(data)),
    ]

    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_chapters = []
    for cid, title, doc in chapters:
        out_file = SHOTS_DIR / f"{cid}.json"
        out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_chapters.append({"id": cid, "title": title, "spec": f"shots/{cid}.json"})
        print(f"Wrote {cid}.json ({len(doc['shots'])} shots, {sum(len(s['lines']) for s in doc['shots'])} lines)")

    manifest = {
        "series": "東京・消えた川の記憶",
        "cardSeconds": 2.2,
        "chapters": manifest_chapters,
    }
    manifest_path = FLYOVER_DIR / "chapters.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
