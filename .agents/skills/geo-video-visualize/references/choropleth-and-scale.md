# 2D / 3D コロプレス図の設計と `choropleth` オーバーレイ

## 1. 誤解を生まない 4 つの設計原則

1. **値の種類で配色を決める**:
   - **量・率・密度**（0 から増える値）: 明るい色から濃い色へ輝度が単調に変わる **順次配色** を使う。
   - **増減・残差・偏差**（0 を跨ぐ値）: 0 を中立色（白・薄灰）に置いた **発散配色**（例: 青–白–赤）を使う。
   - **類型・クラスタ**（LISA の HH/LL/HL/LH 等）: 順序を持たない **定性配色** を使う。
2. **NoData と `0` を混ぜない**:
   - `choroplethColorExpression` は `['typeof', ['get', property]] === 'number'` を検査し、欠損・`null` を必ず `noDataColor`（既定 `#6b7280`）へ逃がす。
3. **時系列・地域間の比較では尺度を固定する**:
   - 年代別や複数都市を並べて比べる場合、各ショットで別々に分位を取り直さず、**全期間・全対象を通じた共通の `breaks` と `heightScale`** を固定する。
4. **人口や面積の大小に注意する**:
   - 広い区画ほど値が大きく見える錯覚を避けるため、面積あたりの密度や人口あたりの率を優先する。

## 2. `choropleth` オーバーレイの書式（ショット JSON）

```json
{
  "type": "choropleth",
  "src": "data/wards.geojson",
  "property": "pop_density",
  "breaks": [0, 5000, 10000, 15000, 20000],
  "colors": ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"],
  "scale": "step",
  "noDataColor": "#6b7280",
  "opacity": 0.85,
  "outline": "#ffffff",
  "outlineWidth": 1.2,
  "extrude": true,
  "heightScale": 0.05,
  "heightBase": 0,
  "rise": [0.1, 0.45],
  "labelProperty": "name",
  "legend": {
    "title": "人口（2020年）",
    "unit": "万人",
    "valueDivisor": 10000,
    "position": "bottom-left",
    "showNoData": false
  },
  "credit": "統計：出典名"
}
```

- `extrude: true` にすると MapLibre の `fill-extrusion` 層で 3D 押し出し棒地図になり、`rise: [t0, t1]` を添えるとショット内で下から滑らかに立ち上がる。
- 3D コロプレスは `pitch: 40〜55` 程度の斜め俯瞰カメラと組み合わせると高さの差が読み取りやすい。
- `legend` を指定すると、`breaks` と `colors` から自動生成（または `labels` で明示指定）された凡例カードを重ねられる（`position` は `top-left` / `top-right` / `bottom-left` / `bottom-right`、`valueDivisor` で単位換算可能）。
- `labelProperty` を指定すると、各ポリゴン重心（`MultiPolygon` は最大面積ポリゴン）にラベルを表示し、3D 押し出しの立ち上がり（`rise`）に合わせて上面へ追従する。`labelFontSize`（最小/既定サイズ）と `labelMaxFontSize` を併記すると、押し出しと連動して値に応じた大きさへ伸びる。
- `breaks` と `colors` は同じ長さ・厳密昇順で指定する。補助計算として `packages/renderer/src/choropleth.ts` の `computeQuantileBreaks` / `computeEqualBreaks` が使える。
