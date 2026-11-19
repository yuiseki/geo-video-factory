# 調査・解析データ (`research/`)

- **取り込み日**: 2026-11-19
- **元データ生成元**: `GeoAI-master-skills` リポジトリ内 `projects/tokyo-river-recall/`
- **内容**: 商用利用可能なオープンデータのみから抽出・検証した東京23区（および関連上水路）の「元々川だった場所」データセット一式。

## 主なファイル

- [report.md](report.md): 分析手法、検証結果、限界事項をまとめた調査報告書
- `outputs/01_current_rivers.geojson`: 現行開渠河川（`LineString`, 947件, 369.79 km）
- `outputs/02_culvert_and_valleys.geojson`: 暗渠河川・DEM抽出谷筋（`LineString`, 590件, 384.31 km）
- `outputs/03_filled_canals.geojson`: 都心・下町の埋立掘割・外濠（`Polygon`, 81件, 20.13 km / 0.993 km²）
- `outputs/04_old_aqueducts.geojson`: 旧上水・用水路（`LineString`, 64件, 55.10 km）
- `outputs/05_former_channels.geojson`: 治水地形分類図の旧河道（`Polygon`, 177件, 5.837 km²）
- `outputs/06_flood_overlap.geojson`: 東京都浸水実績図（1974〜2019年）との空間結合検証結果
- `outputs/summary.json`, `outputs/layer_summary.csv`, `outputs/basin_comparison.csv`: 動画ナレーション・カウンター用の確定集計値
- `outputs/credits.json`: 使用全データセットのライセンス・商用可否・クレジット表記一覧
- `outputs/fig1_*.png` 〜 `fig3_*.png`: 確認用図版（`.gitignore` により Git 管理外）
