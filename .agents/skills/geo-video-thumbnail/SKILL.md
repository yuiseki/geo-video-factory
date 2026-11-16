---
name: geo-video-thumbnail
description: 完成した地理動画から代表フレームを切り出し、1280x720・2MB未満のYouTubeサムネイル（JPG）を設計・自動生成するときに使う。サムネイルの構図、太字タイトルの尺度差、スマホ縮小時の視認性確保に使う。
---

# 地理動画のサムネイル設計と生成

本編動画（`episode.mp4` 等）から最も主題が伝わるフレームを抽出し、HTML テンプレートと Playwright を用いて **1280×720（2MB 未満 JPG）** のサムネイルを再現可能に生成する。構図と文字の造形基準は `geo-video-art-direction` を参照し、公開用の概要欄・チャプター・タグは `geo-video-production`（[publishing.md](../geo-video-production/references/publishing.md)）を使う。

## 手順の概要

1. **代表フレーム抽出**: 本編 MP4 の指定時刻から `ffmpeg` で `hero.png` を切り出す。
2. **構図と文言の確定**: スマホ縮小表示でも読める短い主見出し（8〜14 文字目安）と、地図・地形・対比が隠れない配置を決める。
3. **HTML 描画と JPG 変換**: [assets/thumbnail.html](assets/thumbnail.html) をプロジェクトへコピーして文言を調整し、Playwright で 1280×720 撮影後、`ffmpeg` で 2MB 未満の JPG に変換する。

## 読む資料

- サムネイルの構図基準・生成コマンド・検品項目： [references/thumbnail-design.md](references/thumbnail-design.md)
- 1280×720 描画用の HTML テンプレート： [assets/thumbnail.html](assets/thumbnail.html)

## 完了前の確認

- 横幅 160〜320px 程度に縮小した状態で、主見出しと主図（地形・地図・対比）が一瞬で判別できるか。
- タイトルが地図の核心部分や右下の再生時間バッジ（YouTube UI）と重なっていないか。
- `Noto Sans CJK JP` 等の実ウェイト（Black/Bold）が効いており、背景に文字が負けていないか。
- 使用した背景地図や写真の出典表記（必要時）が漏れていないか、画像サイズが 1280×720・2MB 未満か。
