# ずんだもん・四国めたん（VOICEVOX + PSD 立ち絵）

坂本アヒル氏の立ち絵 PSD と VOICEVOX を使って、ずんだもん・四国めたんの掛け合い動画を作るためのリファレンス。共通の配置・口パク・まばたき仕様は [reaction.md](reaction.md)、VOICEVOX の設定と読み修正は [narration.md](narration.md) を参照する。

## 1. キャラクターの役割と声の設定

| 項目 | ずんだもん | 四国めたん |
|---|---|---|
| 推奨話者キー / ID | `a` / `speaker: 3`（ノーマル） | `b` / `speaker: 2`（ノーマル） |
| 話速の目安 (`speed`) | `1.2` 〜 `1.3` | `1.2` |
| 字幕色の例 | `#ffe94a`（黄） | `#ff9ca7`（ピンク） |
| 立ち絵テンプレート | `characters/zundamon.json` | `characters/metan.json` |

## 2. 立ち絵の書き出し (`psd_sprites.py`)

坂本アヒル氏の立ち絵素材（PSD、PSDTool 対応：ずんだもん 2.3、四国めたん 2.1 で確認済み）を使う。PSD ファイル自体はリポジトリに含めない。

```bash
uv run --with psd-tools python packages/pipeline/narration/psd_sprites.py \
  <project>/characters/zundamon.json \
  tmp/__models/zunda/ずんだもん立ち絵素材2.3.psd \
  <project>/assets/chara/zundamon

uv run --with psd-tools python packages/pipeline/narration/psd_sprites.py \
  <project>/characters/metan.json \
  tmp/__models/metan/四国めたん立ち絵素材2.1.psd \
  <project>/assets/chara/metan
```

用意されている表情: `normal`, `smile`, `surprise`, `trouble`（考える腕）, `point`（指差し）, `sad`（汗）。書き出し後は `<outdir>/sheet.png` を開き、目を閉じた差分が実際に閉じているかを確認する。

## 3. 権利・利用ガイドラインとクレジット

- **立ち絵（坂本アヒル氏）**: 動画での利用と改変は自由、クレジットは任意。
- **キャラクター規約**: [東北ずん子・ずんだもんプロジェクトのガイドライン](https://zunko.jp/guideline.html) に従う。**政治・宗教に関わる使い方（特定の政治家や団体の応援・批判、キャラクターに政治家の評価を言わせること）は禁止。**
- **音声クレジット（必須）**: 画面内および YouTube 概要欄に「VOICEVOX:ずんだもん」「VOICEVOX:四国めたん」を明記する。
