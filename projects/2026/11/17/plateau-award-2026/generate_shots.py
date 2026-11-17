#!/usr/bin/env python3
"""Generate independent shot JSON files for all 17 clips and verify edit-point continuity."""
from __future__ import annotations

import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
SHOTS_DIR = PROJECT / "shots"
MANIFEST = PROJECT / "manifest.json"

BASE_SPEC = {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "base": "seamlessphoto",
    "dem": "gsi",
    "hillshade": False,
}


def cam(center, zoom, pitch, bearing):
    return {"center": center, "zoom": zoom, "pitch": pitch, "bearing": bearing}


def build_clips() -> dict[str, dict]:
    clips: dict[str, dict] = {}

    # S01: 羽村・福生 建物の一斉生成 (3s)
    clips["S01"] = {
        **BASE_SPEC,
        "world": False,
        "credits": ["建物: 国土地理院ベクトルタイル / 国土交通省 PLATEAU (福生市) / © OpenStreetMap contributors"],
        "plateauBuildings": [
            {
                "manifest": "assets/sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
                "reveal": {
                    "center": [139.316, 35.7584],
                    "width": 160,
                    "radius": [[0, -160], [0.5, -160], [2.0, 3500]],
                    "paint": [[0, -200], [1.8, -200], [2.8, 3500]],
                },
            }
        ],
        "shots": [
            {
                "duration": 3,
                "ease": "linear",
                "from": cam([139.319, 35.7525], 15.25, 58, 172),
                "to": cam([139.319, 35.7525], 15.25, 58, 172),
                "overlays": [
                    {
                        "type": "counter",
                        "caption": "羽村・福生 補完建物",
                        "value": 19758,
                        "from": 0,
                        "unit": "棟",
                        "countUp": [0.18, 0.72],
                        "roll": True,
                        "screen": [90, 90],
                        "show": [0.05, 1],
                    }
                ],
            }
        ],
    }

    # B01: 羽村 -> 新宿 (6s) + タイトル「空撮は、書ける。」
    clips["B01"] = {
        **BASE_SPEC,
        "world": False,
        "credits": ["建物: 国土地理院ベクトルタイル / 国土交通省 PLATEAU / © OpenStreetMap contributors"],
        "plateauBuildings": [
            {
                "manifest": "assets/sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
                "reveal": {
                    "center": [139.316, 35.7584],
                    "width": 160,
                    "radius": [[0, 3500]],
                    "paint": [[0, 3500]],
                },
            },
            {
                "manifest": "assets/shinjuku-sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
                "reveal": {
                    "center": [139.6915, 35.69],
                    "width": 200,
                    "radius": [[0, 1000000]],
                    "paint": [[0, -300]],
                },
            },
        ],
        "shots": [
            {
                "duration": 6,
                "path": "fly",
                "ease": "inOut",
                "from": cam([139.319, 35.7525], 15.25, 58, 172),
                "to": cam([139.6915, 35.69], 16.25, 52, -70),
                "overlays": [
                    {
                        "type": "chapter",
                        "kicker": "PLATEAU × オープンデータ",
                        "text": "空撮は、書ける。",
                        "show": [0.15, 0.85],
                    }
                ],
            }
        ],
    }

    # S02: 新宿 PLATEAUの白い建物が変化 (13s)
    clips["S02"] = {
        **BASE_SPEC,
        "world": False,
        "credits": ["建物: 国土交通省 PLATEAU (新宿区) / © OpenStreetMap contributors"],
        "plateauBuildings": [
            {
                "manifest": "assets/shinjuku-sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
                "reveal": {
                    "center": [139.6915, 35.69],
                    "width": 200,
                    "radius": [[0, 1000000]],
                    "paint": [[0, -300], [3.0, -300], [11.5, 2600]],
                },
            }
        ],
        "shots": [
            {
                "duration": 4,
                "ease": "inOut",
                "from": cam([139.6915, 35.69], 16.25, 52, -70),
                "to": cam([139.6915, 35.69], 16.2, 55, -30),
                "overlays": [
                    {"type": "label", "text": "東京都庁", "at": [139.6915, 35.69], "dot": True, "show": [0.05, 1]},
                    {
                        "type": "quote",
                        "text": "PLATEAUの建物に、外観を。",
                        "marks": False,
                        "cps": 40,
                        "screen": [90, 90],
                        "width": 980,
                        "show": [0.1, 1],
                    },
                ],
            },
            {
                "duration": 9,
                "ease": "inOut",
                "from": cam([139.6915, 35.69], 16.2, 55, -30),
                "to": cam([139.685, 35.6925], 16.8, 64, 105),
                "overlays": [
                    {
                        "type": "quote",
                        "text": "屋根は地理院シームレス空中写真。壁と窓は推定。",
                        "marks": False,
                        "cps": 40,
                        "screen": [90, 90],
                        "width": 1160,
                        "show": [0.05, 0.95],
                    }
                ],
            },
        ],
    }

    # B02: 新宿 -> 浅草 (4s)
    clips["B02"] = {
        **BASE_SPEC,
        "world": False,
        "credits": ["建物: 国土交通省 PLATEAU (東京都23区) / 国土地理院ベクトルタイル"],
        "plateauBuildings": [
            {
                "manifest": "assets/shinjuku-sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
                "reveal": {"center": [139.6915, 35.69], "width": 200, "radius": [[0, 1000000]], "paint": [[0, 2600]]},
            },
            {
                "manifest": "assets/asakusa-sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
            },
        ],
        "shots": [
            {
                "duration": 4,
                "path": "fly",
                "ease": "inOut",
                "from": cam([139.685, 35.6925], 16.8, 64, 105),
                "to": cam([139.7967, 35.7147], 17.5, 58, 135),
                "overlays": [],
            }
        ],
    }

    # S03: 浅草・隅田川・両国 (13s)
    clips["S03"] = {
        **BASE_SPEC,
        "world": False,
        "credits": ["建物: 国土交通省 PLATEAU (東京都23区) / 地理院ベクトルタイル / © OpenStreetMap contributors"],
        "plateauBuildings": {
            "manifest": "assets/asakusa-sota/manifest.json",
            "heightOffset": -39,
            "workers": 3,
        },
        "shots": [
            {
                "duration": 4,
                "ease": "inOut",
                "from": cam([139.7967, 35.7147], 17.5, 58, 135),
                "to": cam([139.80075, 35.71014], 16.6, 55, 165),
                "overlays": [
                    {"type": "label", "text": "東京・隅田川", "screen": [230, 90], "style": "tag", "show": [0.05, 1]},
                    {"type": "label", "text": "浅草寺", "at": [139.7967, 35.7147], "dot": True, "show": [0.05, 0.9]},
                ],
            },
            {
                "duration": 6,
                "ease": "linear",
                "keys": [
                    {"t": 0.0, **cam([139.80075, 35.71014], 16.6, 55, 165)},
                    {"t": 0.25, **cam([139.7974, 35.7082], 16.4, 48, 180)},
                    {"t": 0.5, **cam([139.7940, 35.7020], 16.3, 45, 185)},
                    {"t": 0.75, **cam([139.7908, 35.6975], 16.3, 45, 185)},
                    {"t": 1.0, **cam([139.7890, 35.6914], 16.2, 44, 175)},
                ],
                "overlays": [
                    {"type": "label", "text": "東京・隅田川", "screen": [230, 90], "style": "tag", "show": [0, 1]},
                    {"type": "label", "text": "両国", "at": [139.7933, 35.6969], "dot": True, "show": [0.5, 1]},
                ],
            },
            {
                "duration": 3,
                "ease": "inOut",
                "from": cam([139.7890, 35.6914], 16.2, 44, 175),
                "to": cam([139.7912, 35.6925], 15.5, 42, 27),
                "overlays": [
                    {"type": "label", "text": "東京・隅田川", "screen": [230, 90], "style": "tag", "show": [0, 0.95]},
                    {"type": "label", "text": "両国国技館", "at": [139.7933, 35.6969], "dot": True, "show": [0, 0.95]},
                ],
            },
        ],
    }

    # B03: 浅草 -> 羽村 (6s) 着地時点ではPLATEAUのみ表示
    clips["B03"] = {
        **BASE_SPEC,
        "world": False,
        "credits": ["建物: 国土交通省 PLATEAU / © OpenStreetMap contributors"],
        "plateauBuildings": [
            {
                "manifest": "assets/asakusa-sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
            },
            {
                "manifest": "assets/sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
                "reveal": {
                    "center": [139.316, 35.7584],
                    "width": 160,
                    "radius": [[0, -160]],
                    "paint": [[0, -200]],
                },
            },
        ],
        "shots": [
            {
                "duration": 6,
                "path": "fly",
                "ease": "inOut",
                "from": cam([139.7912, 35.6925], 15.5, 42, 27),
                "to": cam([139.3195, 35.7568], 15.85, 62, 160),
                "overlays": [],
            }
        ],
    }

    # S04: 羽村・福生 生成過程を3段階で詳しく見せる (22s)
    clips["S04"] = {
        **BASE_SPEC,
        "world": False,
        "credits": ["建物: 国土地理院ベクトルタイル / 国土交通省 PLATEAU (福生市) / © OpenStreetMap contributors"],
        "plateauBuildings": [
            {
                "manifest": "assets/sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
                "reveal": {
                    "center": [139.316, 35.7584],
                    "width": 160,
                    "radius": [[0, -160], [3.0, -160], [11.0, 2800]],
                    "paint": [[0, -200], [11.0, -200], [19.0, 2800]],
                },
            }
        ],
        "shots": [
            {
                "duration": 22,
                "ease": "inOut",
                "from": cam([139.3195, 35.7568], 15.85, 62, 160),
                "to": cam([139.316, 35.7584], 15.8, 63, 185),
                "overlays": [
                    {"type": "label", "text": "羽村市", "at": [139.312, 35.7625], "show": [0.04, 1]},
                    {"type": "label", "text": "福生市", "at": [139.33, 35.744], "show": [0.04, 1]},
                    {
                        "type": "quote",
                        "text": "PLATEAU未整備の区域では、建物が空白になる。",
                        "marks": False,
                        "cps": 45,
                        "screen": [90, 90],
                        "width": 1080,
                        "show": [0.02, 0.16],
                    },
                    {
                        "type": "quote",
                        "text": "建物の形は、地理院ベクトルタイル。",
                        "marks": False,
                        "cps": 45,
                        "screen": [90, 90],
                        "width": 1120,
                        "show": [0.16, 0.50],
                    },
                    {
                        "type": "quote",
                        "text": "高さは、隣の街のPLATEAUから推定。",
                        "marks": False,
                        "cps": 45,
                        "screen": [90, 210],
                        "width": 1120,
                        "show": [0.24, 0.50],
                    },
                    {
                        "type": "quote",
                        "text": "屋根は地理院シームレス空中写真。壁は推定。",
                        "marks": False,
                        "cps": 45,
                        "screen": [90, 90],
                        "width": 1160,
                        "show": [0.52, 0.96],
                    },
                ],
            }
        ],
    }

    # B04: 東京 -> 大阪 (7s)
    clips["B04"] = {
        **BASE_SPEC,
        "world": True,
        "credits": ["国土地理院タイル / NASA Blue Marble", "建物: 国土交通省 PLATEAU / 地理院ベクトルタイル / © OpenStreetMap contributors"],
        "plateauBuildings": [
            {
                "manifest": "assets/sota/manifest.json",
                "heightOffset": -39,
                "workers": 3,
                "reveal": {
                    "center": [139.316, 35.7584],
                    "width": 160,
                    "radius": [[0, 2800]],
                    "paint": [[0, 2800]],
                },
            },
            {
                "manifest": "assets/osaka-cosmosquare/manifest.json",
                "heightOffset": -38,
                "workers": 3,
            }
        ],
        "shots": [
            {
                "duration": 7,
                "path": "fly",
                "ease": "inOut",
                "from": cam([139.316, 35.7584], 15.8, 63, 185),
                "to": cam([135.4133, 34.6395], 15.9, 42, 0),
                "overlays": [],
            }
        ],
    }

    # S05: 大阪 コスモスクエア・心斎橋・道頓堀 (18s = 5 + 3 + 5 + 5)
    clips["S05"] = {
        **BASE_SPEC,
        "world": False,
        "credits": ["建物: 国土交通省 PLATEAU (大阪市) / 国土地理院ベクトルタイル / © OpenStreetMap contributors"],
        "plateauBuildings": [
            {
                "manifest": "assets/osaka-cosmosquare/manifest.json",
                "heightOffset": -38,
                "workers": 3,
            },
            {
                "manifest": "assets/osaka-minami/manifest.json",
                "heightOffset": -38,
                "workers": 3,
            },
        ],
        "shots": [
            {
                "duration": 5,
                "ease": "inOut",
                "from": cam([135.4133, 34.6395], 15.9, 42, 0),
                "to": cam([135.412, 34.641], 15.6, 48, 25),
                "overlays": [
                    {"type": "quote", "text": "大阪でも、街が立つ。", "marks": False, "cps": 45, "screen": [90, 90], "width": 880, "show": [0.05, 1]},
                    {"type": "label", "text": "コスモスクエア", "at": [135.4133, 34.6395], "dot": True, "show": [0.1, 0.95]},
                ],
            },
            {
                "duration": 3,
                "path": "fly",
                "ease": "inOut",
                "from": cam([135.412, 34.641], 15.6, 48, 25),
                "to": cam([135.5004, 34.6752], 16.9, 48, 180),
                "overlays": [
                    {"type": "quote", "text": "大阪でも、街が立つ。", "marks": False, "cps": 45, "screen": [90, 90], "width": 880, "show": [0, 1]},
                ],
            },
            {
                "duration": 5,
                "ease": "inOut",
                "from": cam([135.5004, 34.6752], 16.9, 48, 180),
                "to": cam([135.5008, 34.6722], 17.0, 48, 180),
                "overlays": [
                    {"type": "label", "text": "心斎橋", "at": [135.5005, 34.6751], "dot": True, "show": [0.05, 0.95]},
                ],
            },
            {
                "duration": 5,
                "ease": "inOut",
                "from": cam([135.5008, 34.6722], 17.0, 48, 180),
                "to": cam([135.5011, 34.6661], 16.6, 35, 180),
                "overlays": [
                    {"type": "label", "text": "道頓堀", "at": [135.5014, 34.6691], "dot": True, "offset": [0, -55], "show": [0.05, 0.95]},
                ],
            },
        ],
    }

    # B05: 大阪 -> 富士山 (8s)
    clips["B05"] = {
        **BASE_SPEC,
        "world": True,
        "exaggeration": 1.5,
        "hillshade": 0.28,
        "credits": ["国土地理院タイル / NASA Blue Marble", "建物: 国土交通省 PLATEAU / 地理院ベクトルタイル / © OpenStreetMap contributors"],
        "plateauBuildings": [
            {"manifest": "assets/osaka-cosmosquare/manifest.json", "heightOffset": -38, "workers": 3},
            {"manifest": "assets/osaka-minami/manifest.json", "heightOffset": -38, "workers": 3},
        ],
        "shots": [
            {
                "duration": 8,
                "path": "fly",
                "ease": "inOut",
                "from": cam([135.5011, 34.6661], 16.6, 35, 180),
                "to": cam([138.7274, 35.3606], 9.8, 50, 30),
                "overlays": [],
            }
        ],
    }

    # S06: 富士山 立体地形の迫力 (10s)
    clips["S06"] = {
        **BASE_SPEC,
        "world": False,
        "exaggeration": 1.5,
        "hillshade": 0.28,
        "credits": ["地理院シームレス空中写真 / 地理院DEM"],
        "shots": [
            {
                "duration": 10,
                "ease": "smooth",
                "from": cam([138.7274, 35.3606], 9.8, 50, 30),
                "to": cam([138.705, 35.358], 11.8, 62, 75),
                "overlays": [
                    {"type": "quote", "text": "山は、地理院DEMから立つ。", "marks": False, "cps": 35, "screen": [90, 90], "width": 980, "show": [0.1, 0.92]},
                    {"type": "label", "text": "富士山（3,776m）", "screen": [1650, 90], "style": "tag", "show": [0.15, 0.9]},
                ],
            }
        ],
    }

    # B06: 富士山 -> 大室山 (4s)
    clips["B06"] = {
        **BASE_SPEC,
        "world": False,
        "exaggeration": 1.2,
        "hillshade": 0.3,
        "credits": ["地理院シームレス空中写真 / 地理院DEM"],
        "shots": [
            {
                "duration": 4,
                "path": "fly",
                "ease": "inOut",
                "from": cam([138.705, 35.358], 11.8, 62, 75),
                "to": cam([139.094, 34.9055], 14.5, 70, -32),
                "overlays": [],
            }
        ],
    }

    # S07: 大室山の四季 (11s) 夏→秋→冬（山焼き）→春、カメラもゆっくり動かす
    omuro_bbox = [139.06494140625, 34.885930940753155, 139.1143798828125, 34.91746688928252]
    clips["S07"] = {
        **BASE_SPEC,
        "world": False,
        "exaggeration": 1.2,
        "hillshade": 0.3,
        "credits": [
            "地理院シームレス空中写真 / 地理院DEM",
            "衛星色度：Copernicus Sentinel-2 L2A (2023-2024)",
            "季節の色は衛星画像を基にした再現",
        ],
        "shots": [
            {
                "duration": 11,
                "ease": "smooth",
                "from": cam([139.094, 34.9055], 14.5, 70, -32),
                "to": cam([139.094, 34.9055], 14.5, 70, -12),
                "overlays": [
                    {"type": "image", "src": "assets/omuro-seasons/summer.jpg", "bbox": omuro_bbox, "maxzoom": 16, "show": [0.0, 0.30], "fade": 0.04},
                    {"type": "image", "src": "assets/omuro-seasons/autumn.jpg", "bbox": omuro_bbox, "maxzoom": 16, "show": [0.25, 0.55], "fade": 0.05},
                    {"type": "image", "src": "assets/omuro-seasons/winter_burn.jpg", "bbox": omuro_bbox, "maxzoom": 16, "show": [0.50, 0.80], "fade": 0.05},
                    {"type": "image", "src": "assets/omuro-seasons/spring.jpg", "bbox": omuro_bbox, "maxzoom": 16, "show": [0.75, 1.05], "fade": 0.05},
                    {"type": "quote", "text": "季節は、衛星の色で着せ替える。", "marks": False, "cps": 45, "screen": [90, 90], "width": 1000, "show": [0.04, 0.96]},
                    {"type": "label", "text": "大室山・夏", "screen": [240, 220], "style": "tag", "show": [0.02, 0.26]},
                    {"type": "label", "text": "大室山・秋", "screen": [240, 220], "style": "tag", "show": [0.27, 0.51]},
                    {"type": "label", "text": "大室山・冬（山焼き）", "screen": [280, 220], "style": "tag", "show": [0.52, 0.76]},
                    {"type": "label", "text": "大室山・春", "screen": [240, 220], "style": "tag", "show": [0.77, 0.98]},
                ],
            }
        ],
    }

    # S08: AIによる映像制作 (11s) - 地図背景は大室山、UIカードは独立overlay (S08_extra.mov) で描画
    clips["S08"] = {
        **BASE_SPEC,
        "world": False,
        "exaggeration": 1.2,
        "hillshade": 0.3,
        "credits": ["地理院シームレス空中写真 / 地理院DEM"],
        "shots": [
            {
                "duration": 11,
                "ease": "linear",
                "from": cam([139.094, 34.9055], 14.5, 70, -12),
                "to": cam([139.094, 34.9055], 14.5, 70, -12),
                "tint": 0.50,
                "overlays": [],
            }
        ],
    }

    # B07: 大室山付近 -> 函館 (9s)
    clips["B07"] = {
        **BASE_SPEC,
        "world": True,
        "exaggeration": 1.0,
        "hillshade": 0.3,
        "credits": ["地理院シームレス空中写真 / 地理院DEM / NASA Blue Marble"],
        "shots": [
            {
                "duration": 9,
                "path": "fly",
                "ease": "inOut",
                "from": cam([139.094, 34.9055], 14.5, 70, -12),
                "to": cam([140.716, 41.768], 14.4, 0, 215),
                "overlays": [],
            }
        ],
    }

    # S09: 函館 地形と市街地の融合 クライマックス (24s)
    clips["S09"] = {
        **BASE_SPEC,
        "world": False,
        "exaggeration": 1.0,
        "hillshade": 0.3,
        "sky": {
            "sky-color": "#1c4a9a",
            "horizon-color": "#d6e6f7",
            "fog-color": "#c9d8e8",
            "sky-horizon-blend": 0.75,
            "horizon-fog-blend": 0.7,
            "fog-ground-blend": 0.85,
            "atmosphere-blend": 0,
        },
        "credits": [
            "地理院ベクトルタイル / 地理院シームレス空中写真 / 地理院DEM",
            "建物属性: © OpenStreetMap contributors（高さ・外観は推定）",
        ],
        "plateauBuildings": {
            "manifest": "assets/hakodate/manifest.json",
            "reveal": {
                "center": [140.719, 41.771],
                "width": 250,
                "radius": [[0, -300], [9.0, -300], [16.0, 7000]],
                "paint": [[0, -300], [13.0, -300], [20.0, 7000]],
            },
        },
        "shots": [
            {
                "duration": 4,
                "ease": "inOut",
                "from": cam([140.716, 41.768], 14.4, 0, 215),
                "to": cam([140.714, 41.765], 14.0, 0, 215),
                "overlays": [],
            },
            {
                "duration": 5,
                "ease": "inOut",
                "from": cam([140.714, 41.765], 14.0, 0, 215),
                "to": cam([140.714, 41.765], 14.0, 55, 215),
                "overlays": [
                    {"type": "label", "text": "函館山", "at": [140.7037, 41.7591], "dot": True, "show": [0.4, 1]},
                ],
            },
            {
                "duration": 15,
                "ease": "inOut",
                "from": cam([140.714, 41.765], 14.0, 55, 215),
                "to": cam([140.714, 41.765], 14.25, 55, 200),
                "overlays": [
                    {"type": "quote", "text": "山ごと、街を描く。", "marks": False, "cps": 35, "screen": [90, 90], "width": 880, "show": [0.15, 0.85]},
                    {"type": "quote", "text": "函館（地理院ベクトルタイル・OSM使用）", "marks": False, "cps": 60, "screen": [90, 920], "width": 920, "show": [0.2, 0.9]},
                ],
            },
        ],
    }

    # S10: OSS無料公開・エンディング (7s)
    clips["S10"] = {
        **BASE_SPEC,
        "world": False,
        "exaggeration": 1.0,
        "hillshade": 0.3,
        "sky": {
            "sky-color": "#1c4a9a",
            "horizon-color": "#d6e6f7",
            "fog-color": "#c9d8e8",
            "sky-horizon-blend": 0.75,
            "horizon-fog-blend": 0.7,
            "fog-ground-blend": 0.85,
            "atmosphere-blend": 0,
        },
        "credits": [
            "国土地理院 / 国土交通省 PLATEAU / © OpenStreetMap contributors / Copernicus Sentinel-2 / VOICEVOX:四国めたん",
        ],
        "plateauBuildings": {
            "manifest": "assets/hakodate/manifest.json",
            "reveal": {
                "center": [140.719, 41.771],
                "width": 250,
                "radius": [[0, 7000]],
                "paint": [[0, 7000]],
            },
        },
        "shots": [
            {
                "duration": 7,
                "ease": "linear",
                "from": cam([140.714, 41.765], 14.25, 55, 200),
                "to": cam([140.714, 41.765], 14.25, 55, 200),
                "tint": 0.68,
                "overlays": [
                    {
                        "type": "chapter",
                        "kicker": "Apache License 2.0  |  github.com/yuiseki/geo-video-factory",
                        "text": "geo-video-factory",
                        "show": [0.05, 1.0],
                    },
                    {
                        "type": "quote",
                        "text": "この映像を作るソフトウェアを、無料で公開しています。",
                        "marks": False,
                        "cps": 60,
                        "screen": [400, 180],
                        "width": 1120,
                        "show": [0.05, 1.0],
                    },
                ],
            }
        ],
    }

    return clips


def endpoint_cameras(spec: dict) -> tuple[dict, dict]:
    first = spec["shots"][0]
    last = spec["shots"][-1]
    entry = first.get("from") or first["keys"][0]
    exit_ = last.get("to") or last["keys"][-1]
    return (
        {k: entry[k] for k in ("center", "zoom", "pitch", "bearing")},
        {k: exit_[k] for k in ("center", "zoom", "pitch", "bearing")},
    )


def main() -> None:
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    clips = build_clips()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    total_sec = 0
    prev_exit = None
    prev_id = None
    for item in manifest["clips"]:
        cid = item["id"]
        spec = clips[cid]
        dur = sum(s["duration"] for s in spec["shots"])
        assert dur == item["duration"], f"{cid}: shot duration {dur} != manifest {item['duration']}"
        total_sec += dur

        entry, exit_ = endpoint_cameras(spec)
        assert entry == item["entry_camera"], f"{cid}: entry {entry} != manifest {item['entry_camera']}"
        assert exit_ == item["exit_camera"], f"{cid}: exit {exit_} != manifest {item['exit_camera']}"
        if prev_exit is not None:
            assert entry == prev_exit, f"Discontinuity {prev_id} -> {cid}: {prev_exit} != {entry}"
        prev_exit = exit_
        prev_id = cid

        out_path = SHOTS_DIR / f"{cid}.json"
        out_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path.name} ({dur}s)")

    print(f"\nVerified all {len(manifest['clips'])} clips! Total duration: {total_sec}s (< 180s)")


if __name__ == "__main__":
    main()
