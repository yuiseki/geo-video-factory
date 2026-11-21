# packages/blender (試作)

ショット JSON の 1 フレームを Blender で描く試作です。MapLibre + Three.js のレンダラー (`packages/renderer/`) と同じ JSON を読み、光の扱いだけを Blender (EEVEE / Cycles) に任せたときの見た目と時間を比べるために作りました。

```bash
blender -b --factory-startup -P packages/blender/render_plateau_shot.py -- \
  --shot <shot.json> --project-dir <ショットのパスの基準ディレクトリ> \
  --out <frame.png> --engine EEVEE --samples 32
```

- 座標とカメラの計算は `packages/pipeline/blender_geo.py` にあり、bpy なしで単体テストしています (`packages/pipeline/tests/test_blender_geo.py`)。
  - MapLibre のカメラ (center、zoom、pitch、bearing、縦の fov) を、地面 z=0 の上の Blender のカメラに変換します。
  - PLATEAU のタイルは、glTF の取り込み座標 (= `rtc` からの ECEF の差) を ENU に変換します。レンダラーの `gltfVertexToEnu` と同じ式です。
- 読む項目: `plateauBuildings.manifest` / `heightOffset` / `groundPlane` / `billboards` / `streetProps`、`fov`、`sky`、`shots[0].keys`。
- 読まない項目: `facadeTextures` (壁面アトラスのシェーダー)、`night` (窓の明かり)、`overlays`、地図タイル。

## 計測 (2026-11-21、Apple M4 Max、1280×720、v31 の構図)

| エンジン | 設定 | 1 フレームの時間 |
|---|---|---|
| EEVEE | 32 サンプル、レイトレーシングあり | 約 1.5〜4 秒 |
| Cycles (Metal) | 128 サンプル、デノイズ | 約 165 秒 |

PLATEAU 20 タイルの読み込みに約 1 秒かかります。
