# 伊豆の温泉と昭和のゴールドラッシュ：空間データ収集・品質監査・空間解析報告

## 問い

伊豆半島（静岡県11市町および沼津市・三島市の半島側エリア、面積 1,398.49 km²）における温泉・温泉旅館 POI の分布構造と主要鉱山・金山の空間的近接性、1978年持越鉱山鉱滓ダム決壊の流下経路、および昭和期（1931〜1987年）の産金推移はどうなっているか。

## 結論

| 項目 | 主な結果（出所） |
|---|---|
| 温泉・温泉旅館 POI 数 | 388 件（温泉旅館・ホテル 298 件、公衆浴場・日帰り湯 78 件、源泉 12 件）（[onsen_pois.geojson](outputs/onsen_pois.geojson)） |
| 温泉 POI の点パターン | 最寄隣距離比 R = 0.4173（実測平均 0.3961 km 対 CSR 期待 0.9493 km、z = -21.96）。Ripley の L(r)-r は半径 1 km（2.848 km）、2 km（2.861 km）、5 km（0.988 km）で 95% 包絡線を上回る集積（[spatial_stats.json](outputs/spatial_stats.json)） |
| 鉱山から最寄り温泉までの距離 | 9 鉱山の中央値 0.338 km（平均 1.425 km、最大 4.625 km）。半島内ランダム点（中央値 2.244 km、平均 2.418 km）より近い（[spatial_stats.json](outputs/spatial_stats.json)） |
| 坑内温泉起源・近接の鉱山 | 9 鉱山のうち 4 鉱山（土肥金山、大仁鉱山、河津鉱山（蓮台寺鉱山）、湯ヶ島鉱山）で坑内湧出・温泉供給の記録があり、半径 3 km 圏内に 6〜25 件の温泉 POI が位置する（[nearest_onsen_analysis.csv](outputs/nearest_onsen_analysis.csv)） |
| 統一メッシュと MAUP | 2 km 格子（424 セル、0 セル率 75.9%）の温泉数 Moran's I = 0.111（k=6、pseudo p = 0.003）。5 km 格子（84 セル、0 セル率 32.1%）では I = -0.0242（pseudo p = 0.676）となり、空間自己相関の有無は集計単位に依存する（[spatial_stats.json](outputs/spatial_stats.json)） |
| 1978年持越鉱山流下経路 | ほおずき沢付近（標高 479.2 m）から持越川（7.094 km）、狩野川合流点（183.55 m）を経て大仁付近（23.791 km、18.4 m）、駿河湾河口（46.084 km、3.21 m）へ単調降下する 46.084 km の経路を接続（[kanogawa_spill_route.geojson](outputs/kanogawa_spill_route.geojson)） |
| 昭和期産金・価格推移 | 1931〜1987 年（57 年行）を整理。政府買上・国内平均価格は 1932 年 2.57 円/g から 1938 年 3.85 円/g、1980 年 4,499 円/g へ上昇。国内産金量は 1940 年前後約 24.5 トンを頂点に 1943 年金鉱業整備令後 1945 年約 1.5 トンへ急減（[showa_gold_timeline.csv](outputs/showa_gold_timeline.csv)） |

> [!NOTE]
> 鉱山と温泉の近接性は火山性熱水活動という地質的共通背景を反映した空間的関連であり、因果効果の推定ではない。また OSM の POI 密度には観光地ほど登録が多い観測バイアスが混入している可能性がある（11 市町の人口密度と温泉密度の Spearman 相関 ρ = 0.3091、[spatial_stats.json](outputs/spatial_stats.json)）。

![伊豆半島の温泉POI・主要鉱山・1978年持越鉱山流下経路](outputs/izu_onsen_mines_map.png)

![1978年持越鉱山・狩野川流下経路の標高プロファイルと温泉POIのRipley L(r)-r](outputs/kanogawa_and_ripley.png)

## データ

- **OpenStreetMap POI・河川網**: `overpass.yuiseki.net`（snapshot `2025-09-14T23:59:55Z`、取得日 `2026-11-19`、ODbL-1.0、`© OpenStreetMap contributors`）。bbox 内の重複除去後 675 件から 13 市町内 581 件を抽出し、沼津市（`lat > 35.085` の非半島側 13 件）・三島市（`lat > 35.120` の非半島側 14 件）、非施設タグ（バス停・駐車場等 57 件＋29 件）、ビジネスホテル・非温泉民宿等（52 件）、鉱山・観光施設等（7 件）、無名ホテル等（8 件＋10 件）、200 m 以内重複（13 件）を除き、388 件を採択した（[manifest.json](outputs/manifest.json)）。
- **行政区域**: `yuiseki/jp-admin-2026-09`（`card_revision: e6c87b1d`、2020 年国勢調査人口・2026-09 自治体境界、CC-BY-4.0）。静岡県 13 市町（熱海市、伊東市、東伊豆町、河津町、下田市、南伊豆町、松崎町、西伊豆町、伊豆市、伊豆の国市、函南町、および沼津市 `lat <= 35.085`・三島市 `lat <= 35.120` クリップ域）を対象とし、神奈川県湯河原町・真鶴町・箱根町は除外した（[izu_municipalities_summary.geojson](outputs/izu_municipalities_summary.geojson)）。
- **主要鉱山 9 件**: OSM（土肥金山・龕附天正金鉱の 2 件のみ坑口・施設として登録）に加え、Wikipedia・静岡県史・伊豆半島ジオパーク資料から 7 件を補完した（[mines.geojson](outputs/mines.geojson)）。座標精度は `exact_portal` 2 件、`site_area` 4 件、`district_centroid` 3 件（縄地鉱山・河津鉱山・湯ヶ島鉱山）。
- **標高タイル**: 国土地理院 `dem_z14`（Web メルカトル約 9.55 m 格子、取得日 `2026-11-19`、PDL 1.0）。
- **産金・価格年表**: 田中貴金属工業・日本銀行・産総研地質調査総合センター等の公表基準値（[showa_gold_timeline.csv](outputs/showa_gold_timeline.csv)）。

## 方法

1. **データ収集・品質監査・観測バイアス監査**: Overpass API で取得した地物を `jp-admin-2026-09` で空間結合し、ビジネスホテル・非施設ノイズ・200 m 以内重複を明示規則で除外した。OSM 上の鉱山網羅率は 2/9 件（22.2%）にとどまるため、外部史料で補完し `coord_precision` を付与した。
2. **空間関係・点パターン・空間自己相関**: UTM Zone 54N（EPSG:32654）に投影し、温泉 POI の最寄隣距離比（NNI）と Ripley の $L(r)-r$（CSR 199 回シミュレーション、`seed=42`）を算出した。また 2 km 格子（424 セル）および MAUP 確認用の 5 km 格子（84 セル）を作成し、k 近傍（$k=3, 6, 12$、999 回並べ替え）の Global Moran's I を計測した。鉱山から温泉への距離は WGS84 測地線距離（`pyproj.Geod`）で算出し、半島内ランダム点 1,000 点の分布と比較した。
3. **1978 年流下経路接続**: OSM の `持越川`・`猫越川`・`狩野川` の有向線分を有向グラフとして接続し、持越鉱山最寄りの持越川点から駿河湾河口までを BFS でトレースして 3 区間に分割し、各代表点の標高を GSI `dem_z14` から取得した。

## 失敗の型

| ID | 判定 | 根拠 |
|---|---|---|
| F1 | 確かめた | 581 件の市町内抽出から 388 件採択までの除外（180 件）・重複除去（13 件）の総和が一致し、欠損値は 0 ではなく `null` で記録した（[manifest.json](outputs/manifest.json)） |
| F2 | 確かめた | 温泉 POI の集積は CSR 199 回包絡線、鉱山近接性は半島内ランダム点 1,000 点（中央値 2.244 km）と同一範囲で比較した（[spatial_stats.json](outputs/spatial_stats.json)） |
| F3 | 当てはまらない | 機械学習による予測や交差検証を行っていない |
| F4 | 確かめていない | 観光地ごとの OSM 登録努力差を統制した真値との照合は行っていない |
| F5 | 確かめた | 5 km 格子で Moran's I が負（-0.0242）になる点は MAUP（424 セル対 84 セルの平滑化）として解釈した（[spatial_stats.json](outputs/spatial_stats.json)） |
| F6 | 確かめた | 報告内の半径（1, 2, 5, 10, 15, 20 km）、$k$（3, 6, 12）、クリップ緯度（35.085, 35.120）はスクリプトの実装値と一致している |
| F7 | 確かめた | 2 km 格子と 5 km 格子・市町集計の 3 単位を並置し、結論の単位依存性を確認した（[spatial_stats.json](outputs/spatial_stats.json)） |
| F8 | 確かめた | 要点の表の全数値に出力ファイルへのリンクを付し、`check_project.py` で照合した |
| F9 | 確かめた | OSM スナップショット日時（2025-09-14）、`jp-admin-2026-09` リビジョン（`e6c87b1d`）、GSI DEM 取得日（2026-11-19）を明記した（[manifest.json](outputs/manifest.json)） |

## 確かめていないこと

- **F4（観測バイアスと真値の分離）**: 自治体別の登録温泉旅館数・源泉数台帳（静岡県温泉台帳等）との全件突き合わせを行っていないため、OSM POI の欠落率（omission）と観光地バイアスの正確な分離は未確認。
- **坑口座標の精密測量**: 鉱山 9 件のうち 3 件（縄地鉱山・河津鉱山・湯ヶ島鉱山）は `district_centroid` であり、1 km 圏内の温泉数（[nearest_onsen_analysis.csv](outputs/nearest_onsen_analysis.csv)）には数百 m〜1 km 程度の位置誤差が含まれうる。
- **年次連続統計の補完**: `showa_gold_timeline.csv` の 1931〜1987 年全年のうち、基準年以外の年次数値は公的年鑑の原表未取得のため `null` としている。
