---
name: geo-video-materials
description: 地理動画に使うイラスト（いらすとや等）、写真（Wikimedia Commons・個人写真）、ピクトグラム、立ち絵、過去地図などの素材を収集・監査する。取得方法、ライセンス確認、重複除外、EXIF座標抽出、Gyazo等の画像ID管理、出典表記が必要なときに使う。
---

# 地理動画の素材収集と権利管理

外部素材や個人写真を安全かつ再現可能に収集し、重複・権利・出典・秘密情報（画像 ID）を管理する。

## 責務と使い分け

- **素材ごとの取得手順と出典書式**: いらすとや、Wikimedia Commons、EXPERIENCE JAPAN PICTOGRAMS、立ち絵、過去空中写真の取得方法と規約。→ [references/sourcing.md](references/sourcing.md)
- **権利確認・重複監査・EXIF・Gyazo ID 管理**: 見た目の重複判定、CC0 の適用範囲、元画像の EXIF と `photo_geo.py`、`.gitleaks.toml` の許可リスト運用。→ [references/rights-and-audit.md](references/rights-and-audit.md)

- **写真の置き場**: 取った写真はプロジェクトに置かず、共有キャッシュの `tmp/.cache/photos/<取得元>/<ID のハッシュ>/` に一度だけ置く (`packages/pipeline/photos/photo_store.py`、原本と出典の `meta.json`)。プロジェクトのマニフェストは各行の `photo` (`commons:<ファイル名>`、`flickr:<番号>` など) で写真を指す。使用禁止の写真 (`photo_blocklist.tsv`) は置き場に入らない。`python -m photos.catalog_download` は置き場に取り、すでにある写真は取り直さない。
- **映像に貼る写真は CC0 と PD だけ**: CC BY と CC BY-SA は `--registration-only` を付けたときだけ集め、別の置き場から SfM の位置合わせにだけ使う。判断の理由、中間生成物の扱い、仕組み。→ [references/registration-only-photos.md](references/registration-only-photos.md)
- **実写真から人と車を消す**: SAM 3.1 で人・看板・車を分けて検出し、看板の中の人を残し、LaMa で塗る。やめた方法とその理由、検品の観点。→ [references/people-removal.md](references/people-removal.md)

## 関連スキルとの境界

- 動画全体の企画・章構成・パイプライン実行・公開用概要欄の作成は `geo-video-production` を使う。
- 集めた写真やイラストを画面上のどこにどう配置するか（`photo_marker` / `sticker` / `panel` の演出や画面文法）は `geo-video-visuals` を使う。
- 立ち絵の表情差分・口パク・まばたき・音声との同期は `geo-video-narration` を使う。
- 地理院写真や標高タイルの描画設定は `geo-video-renderer` / `geo-video-3d-terrain` を使う。
