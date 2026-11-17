# 心斎橋・道頓堀からコスモスクエアへ

浅草・両国と同じ PLATEAU + 地理院建物外形・標高・空中写真 + OSM 属性の手法を使うための素材確認。現段階では、心斎橋・道頓堀とコスモスクエアの2区域を個別に取得し、3地点の静止画を出力する。区域間の経路と動画はまだ作っていない。

## 静止画の再生成

Node.js、Playwright の Chromium、ffmpeg、および `packages/pipeline/requirements-dev.txt` の Python 依存関係が必要。資源制限はホストの規則に従う。

```sh
export GVF_PYTHON=/path/to/python
export OVERPASS_URL=https://overpass.yuiseki.net/api/interpreter
bash projects/2026/11/17/tour-shisaibashi-dotonbori-cosmosqare/previews.sh
```

`minami` または `cosmosquare` を引数に指定すると該当区域のみ処理する。データは各区域の `assets/` にキャッシュし、静止画は `out/<地点>.v0.1.3/frames/00000.jpg` に出力する。出力済みの同じディレクトリは上書きされない。

## データと範囲

- PLATEAU 大阪市2025年度、建物ごとの最大 LOD2：`https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/27100-bldg-maxlod2-2025/tileset.json`
- 心斎橋・道頓堀: `[135.492, 34.664, 135.513, 34.680]`（西・南・東・北）
- コスモスクエア: `[135.403, 34.635, 135.424, 34.650]`
- 地理院最適化ベクトルタイルの建物外形と標高、地理院空中写真、© OpenStreetMap contributors の建物属性。
- 建物取得と補完は `projects/2026/11/17/tour-asakusa-ryogoku/prepare.py` と共通パイプラインを使う。建物の外壁・窓・屋根の形と不足する高さは推定を含む。PLATEAU の高さには暫定的に -38 m の補正を使用し、実際の地面との整合は今後検証する。

2026-11-17 の取得では、交差タイル内に含まれる建物 ID と補完建物はそれぞれ以下の通り。交差タイル全体の数であり、指定範囲内の厳密な棟数ではない。

| 区域 | PLATEAU 建物 ID | 地理院外形からの補完 |
|---|---:|---:|
| 心斎橋・道頓堀 | 16,602 | 545 |
| コスモスクエア | 850 | 58 |

大阪側のデータは写真テクスチャが少なく、静止画では灰色の建物が多い。画面の色や高さの正確さは、動画を作る前に検証・調整が必要。
