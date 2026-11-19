# 調査資料インデックス：伊豆の温泉と昭和のゴールドラッシュ

調査日: 2026-11-19  
対象プロジェクト: `projects/2026/11/19/izu-hot-spring-and-gold/`

## ファイル一覧

| ファイル | 内容 |
|---|---|
| [geology_and_hotsprings.md](geology_and_hotsprings.md) | 伊豆半島の地史（海底火山とプレート衝突）、熱水鉱床と温泉の共通メカニズム、主要温泉一覧 |
| [mines_and_goldrush.md](mines_and_goldrush.md) | 伊豆半島の主要鉱山・金山一覧（座標付き）、昭和戦前期の産金政策（産金法・金買入価格・産金量・金鉱山整備令） |
| [disasters_and_negative_history.md](disasters_and_negative_history.md) | 昭和期の負の歴史（1937年持越坑内ガス事故、1944〜45年宇久須の強制労働、1958年狩野川台風、1978年伊豆大島近海の地震・鉱滓ダム決壊） |
| [data/](data/) | `GeoAI-master-skills`（`projects/izu-onsen-goldrush`）から取り込んだ検証済み GeoJSON / CSV / JSON データ一式（[geoai_report.md](data/geoai_report.md), [manifest.json](data/manifest.json)） |
| `geo/nominatim_places.json` | `nominatim.yuiseki.net` への初回座標検索結果（2026-11-19 取得） |
| `geo/nominatim_izu_bounded.json` | 伊豆半島範囲（`viewbox=138.65,35.18,139.18,34.55`）指定での再検索結果（2026-11-19 取得） |
| `geo/kanogawa_overpass.json` | `overpass.yuiseki.net` から取得した持越川（5 way）・狩野川（41 way）の河川形状データ（2026-11-19 取得） |

## 空間データ取得記録（OSM サービス）

- 取得日: 2026-11-19
- 利用サービス:
  - Nominatim (`https://nominatim.yuiseki.net/search`)
  - Overpass API (`https://overpass.yuiseki.net/api/interpreter`)
- データ時点の注記: `osm-services.md` 記録上、両サービスの OSM データは 2025-09-14 時点。また、初回検索で同名他県施設が返った地点（大仁鉱山・大仁温泉・蓮台寺温泉・熱海温泉・伊東温泉・堂ヶ島温泉）は、伊豆半島のバウンディングボックスを指定して再取得した。
- 出典表記: `© OpenStreetMap contributors`

## 企画書記載 URL の確認メモ

- 企画メモに挙げられていた財務省 PDF（`https://www.mof.go.jp/pri/research/seminar/fy2022/lm20220519.pdf`）は、関野満夫『日本の戦争財政』に基づく「敗戦後日本の巨額の戦時国債はどのように処理されたのか（戦後インフレ・財産税）」の資料であり、昭和戦前期の産金奨励・金鉱山開発を直接扱う資料ではなかった。そのため、産金政策については産金法・日本銀行金買入法・経済史資料等から調査を補完している。
