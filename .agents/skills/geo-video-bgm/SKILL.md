---
name: geo-video-bgm
description: 地理解説動画のBGM選定・ローカル合成、VOICEVOX音声に対するFFmpegダッキング（sidechaincompress）、-14 LUFS前後への音量マスタリングと出典管理を設計するときに使う。BGMが声を邪魔する、複数章を結合した後にBGMを重ねたいときに使う。
---

# 地理動画の BGM と音量マスタリング

声（VOICEVOX）の聞き取りやすさを最優先に保ちつつ、動画のテンポと雰囲気を支える BGM の用意、自動ダッキング、音量正規化を設計する。セリフ・字幕・立ち絵の制御は `geo-video-narration`、章の結合パイプラインは `geo-video-production` を使う。

## 設計の原則

1. **声の帯域と音量を邪魔しない**: 解説動画では声が主役。BGM 単体を一定音量で敷くだけでなく、発話中は自動で音量を下げる（ダッキング）。
2. **章パイプラインとは結合後に混ぜる**: `chapter_pipeline.py` は章結合時に `bgm` 指定を受け付けないため、結合済み動画（`episode.mp4`）に対して後処理でダッキング＋音量正規化を行う。
3. **権利と出典を明確にする**: 外部音源を使う場合は利用規約・クレジット表記条件を記録し、権利確認を省きたい場合はローカルでライセンスクリーンな BGM を合成する。

## 読む資料

- FFmpeg `sidechaincompress` ダッキングと `-14 LUFS` 音量調整： [references/ducking-and-loudness.md](references/ducking-and-loudness.md)
- ローカル BGM 合成と外部 BGM 選定・出典管理： [references/local-bgm.md](references/local-bgm.md)

## 完了前の確認

- 声が出ている区間で BGM が自然に下がり、無音区間（章間・導入・余白）で不自然に跳ね上がらないか。
- 完成動画の統合ラウドネスが目標値（-14 LUFS 前後、トゥルーピーク -1.5 dBTP 以下）に収まっているか。
- 使用した BGM の取得元・作者・ライセンス・クレジット表記を概要欄と記録ファイルに残したか。
