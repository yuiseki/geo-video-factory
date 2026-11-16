# ゆっくり（霊夢・魔理沙：PNG パーツ立ち絵 + Open JTalk / 合成音声）

たぬき式ゆっくりのような部位別 PNG パーツ立ち絵と、Open JTalk 等の音声合成を組み合わせて、霊夢・魔理沙の掛け合い動画を作るためのリファレンス。共通の配置・口パク・まばたき仕様は [reaction.md](reaction.md) を参照する。

## 1. キャラクターの役割と掛け合い設計

| 項目 | 魔理沙（解説役・左側推奨） | 霊夢（聞き役・右側推奨） |
|---|---|---|
| 立ち絵テンプレート | `characters/marisa.json` | `characters/reimu.json` |
| 口調の目安 | 一人称「私」。「〜だぜ」「〜なんだ」「〜だな」 | 一人称「私」。「〜なの？」「〜ね」「〜じゃない」 |
| 声質の目安 | 低めで落ち着いた声 | 高めで少し速い声 |

- **掛け合いのリズム**: 「霊夢の疑問 → 魔理沙の解説 → 霊夢の反応」を基本とし、3〜4 セリフごとにたとえ話・驚き・ツッコミを入れる。
- **表情戻し**: 話していないキャラは直前に話した表情のまま残るため、聞き役に `think` や `trouble` を付けた場合は、次のそのキャラのセリフで `normal` に戻す。

## 2. 立ち絵の書き出し (`part_sprites.py`)

部位ごとのフォルダ（`体`, `顔色`, `口`, `目`, `髪`, `眉`, `他`）に分かれた PNG パーツを重ねて、レンダラー互換の `<face>_<eyes o|c>_<mouth o|c>.png` と `sheet.png` を生成する。

```bash
python3 packages/pipeline/part_sprites.py \
  <project>/characters/reimu.json \
  "tmp/__models/たぬき式ゆっくり/たぬき霊夢" \
  <project>/assets/chara/reimu

python3 packages/pipeline/part_sprites.py \
  <project>/characters/marisa.json \
  "tmp/__models/たぬき式ゆっくり/たぬき魔理沙" \
  <project>/assets/chara/marisa
```

- `part_sprites.py` は全差分のバウンディングボックス和集合（union bbox）で一括切り出しし、四隅に `alpha=1` ピクセルを打って位置ずれを防ぐ。また `min_width: 820` により、帽子で横幅の広い魔理沙と霊夢の顔サイズを揃える。
- 書き出し後は必ず `sheet.png` を開き、閉眼差分・口パク・顔位置が揃っているか確認する。

## 3. 音声合成（Open JTalk）

ゆっくり風の音声をローカルで生成する場合、Homebrew 版 `open_jtalk` または Python 版 `pyopenjtalk`（HTS Voice "Mei" 等）が利用できる。

- **HTS Voice の声質分離**: `pyopenjtalk.tts(text, speed=..., half_tone=...)` 等でピッチ（`half_tone`: 霊夢は高め `+2.0` 前後、魔理沙は低め `-3.0` 前後）や話速を調整して 2 人の声を聞き分けやすくする。
- **読みの確認**: 固有名詞や同音異義語（「間」「光」「方」など）の読み間違いは `speech` でひらがな・カタカナに直して防ぐ（詳細は [narration.md](narration.md)）。

## 4. 権利・利用ガイドラインとクレジット

- **たぬき式ゆっくり（https://tanukiyukkuri.github.io/tanukitachie ）**: `TERMS.txt`（版: 2026-03-18）では動画・収益化・商用利用・改変可、クレジット任意（推奨表記: `たぬき式ゆっくり: https://tanukiyukkuri.github.io/tanukitachie`）。素材や改変物を再配布する場合は同梱 `README.txt` と `TERMS.txt` を含める。パーツ PNG 本体はリポジトリに含めない。
- **東方Project 二次創作ガイドライン（https://touhou-project.news/guideline/ ）**: たぬき霊夢・たぬき魔理沙は東方Project の二次創作素材のため、**二次創作であることを画面末尾や概要欄に明記して公式コンテンツと誤解させない**、また**個人の思想・政治的主張の発信に使わない**。
- **Open JTalk / HTS Voice クレジット**: Open JTalk および HTS Voice "Mei"（© Nagoya Institute of Technology, CC BY 3.0）を使用した場合は、概要欄・クレジットに表記する。
