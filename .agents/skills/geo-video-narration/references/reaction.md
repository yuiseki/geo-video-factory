# リアクションワイプ (話し手の立ち絵を隅に出す)

画面の右下 (字幕の帯の上) に、2 人の話し手の立ち絵を並べる。

- 話している側: 明るく、少し大きい。声の大きい所で口が開く。セリフの頭で少し跳ねる。表情はセリフの `face`。
- 聞いている側: 暗くして少し小さい。表情はセリフの `react`。
- 2 人とも、別々の間合いでまばたきする (時刻だけで決まるので、同じコマは何度書き出しても同じ)。
- 出ているあいだ、右下の出典は左下へ移る。

手本: 図解中心の地図解説動画で、右下に出続けるキャラクター (場面ごとに驚く、本を読む、両手を上げる)。用語は [graphics.md](../../geo-video-visuals/references/graphics.md) の「リアクションワイプ」。

## 素材の選択肢

レンダラーが読み込む形式は `<project>/assets/chara/<名前>/<表情>_<目 o|c>_<口 o|c>.png` で共通のため、以下のいずれの形式でもキャラクターを追加・切り替えできる。

### 1. PSD 立ち絵 (坂本アヒル氏 ずんだもん・四国めたん等)

坂本アヒルの立ち絵素材 (PSD、PSDTool 対応)。ずんだもん 2.3、四国めたん 2.1 で確かめた。readme では、動画での利用と改変は自由、クレジットは任意。あわせて東北ずん子・ずんだもんプロジェクトのガイドライン (https://zunko.jp/guideline.html) に従う。政治・宗教に関わる使い方 (特定の政治家や団体の応援・批判) は禁止。キャラクターに政治家の評価を言わせない。

配布元の uploader.jp は 2026-11-25 で終わる。写しの置き場は本人のメモにある。PSD はリポジトリに入れない。

### 2. PNG パーツ重ね合わせ立ち絵 (たぬき式ゆっくり 霊夢・魔理沙・サンプル等)

部位ごとのフォルダ（`体`, `顔色`, `口`, `目`, `髪`, `眉`, `他`）に分かれた PNG パーツを重ねて書き出す方式。テンプレートに `characters/reimu.json` / `characters/marisa.json` の雛形がある。

- たぬき式ゆっくり（https://tanukiyukkuri.github.io/tanukitachie ）の `TERMS.txt`（版: 2026-03-18）では動画・収益化・商用利用・改変可、クレジットは任意（推奨表記あり）。改変・再配布時は同梱 `README.txt` と `TERMS.txt` を含める。
- 「たぬき霊夢」「たぬき魔理沙」等の東方Project 二次創作素材は、**東方Project の二次創作ガイドライン (https://touhou-project.news/guideline/)** に従い、二次創作であることを明記し、個人の思想発信に使わない。パーツ PNG そのものは成果物やリポジトリに含めない。

### 3. 既存 PNG 差分や簡易合成素材の直接配置

すでに切り出し済みの立ち絵 PNG や、素材のない環境での試作用簡易立ち絵を使う場合は、`<表情>_<o|c>_<o|c>.png` のファイル名で `assets/chara/<名前>/` へ配置すればそのまま利用できる。

## 立ち絵を書き出す

### PSD から書き出す (`psd_sprites.py`)

`packages/pipeline/psd_sprites.py` が、表情ごとに口 (開く・閉じる) と目 (開く・閉じる) の 4 枚を書き出す。psd-tools は共通依存に入れていないので uv で動かす。次のコマンドはリポジトリのルートで実行する。

```bash
uv run --with psd-tools python packages/pipeline/psd_sprites.py <project>/characters/zundamon.json tmp/zunda/ずんだもん立ち絵素材2.3.psd <project>/assets/chara/zundamon
uv run --with psd-tools python packages/pipeline/psd_sprites.py <project>/characters/metan.json tmp/metan/四国めたん立ち絵素材2.1.psd <project>/assets/chara/metan
```

### PNG パーツフォルダから書き出す (`part_sprites.py`)

`packages/pipeline/part_sprites.py` は `order` 順に PNG パーツを重ね、全差分のバウンディングボックス和集合（union bbox）で切り出して位置ずれを防ぎ、四隅に `alpha=1` ピクセルを置いてトリミングズレを抑える。帽子などで左右幅が異なるキャラ間は `min_width` で顔サイズを揃える。

```bash
python3 packages/pipeline/part_sprites.py <project>/characters/reimu.json "tmp/__models/たぬき式ゆっくり/たぬき霊夢" <project>/assets/chara/reimu
python3 packages/pipeline/part_sprites.py <project>/characters/marisa.json "tmp/__models/たぬき式ゆっくり/たぬき魔理沙" <project>/assets/chara/marisa
```

どちらのツールも `assets/chara/<名前>/<表情>_<目 o|c>_<口 o|c>.png` と、全部を並べた `sheet.png` を生成する。書き出したら必ず `sheet.png` を目で見て、目を閉じた版が閉じているか、表情と位置が揃っているかを確認する。

### characters/*.json

| キー | 中身 |
|---|---|
| `crop` | 切り出す範囲 [x0, y0, x1, y1] (PSD の画素)。頭から腰まで |
| `width` | 書き出す幅 (px) |
| `base` | どの表情でも使う選択。グループの道筋 → 見せる子。`"/"` は一番上の `*` (服) |
| `blink` | 目を閉じた版で上書きする選択 (例 `{"目": "UU"}`) |
| `faces` | 表情ごとに `select` (base への上書き)、`mouth_open`、`mouth_closed`、`on`/`off` (記号など、`*` でない層の表示) |

PSDTool の決まり: 名前が `*` で始まる層は兄弟のうち 1 つだけ見せる、`!` は常に見せる。名前は `*` `!` を外して書く。選択は base → 表情 → 口 → 閉じた目の順に当てるので、あとのものが勝つ。グループ自身を見せるかどうかは親の選択で決まる (目セットの中の黒目を選んでも、閉じた目で隠した目セットは戻らない)。

用意した表情: `normal` `smile` `surprise` `trouble` (考える腕) `point` (指差し) `sad` (汗)。

## JSON

```json
"reaction": {
  "characters": {
    "a": { "sprites": "assets/chara/zundamon", "seed": "zundamon" },
    "b": { "sprites": "assets/chara/metan", "seed": "metan" }
  },
  "order": ["b", "a"],
  "height": 240,
  "side": "right",
  "bottom": 150
},
"shots": [
  { "lines": [
      { "voice": "a", "text": "ヤサイマシマシができない日があるのだ！？", "face": "surprise", "react": "normal" },
      { "voice": "b", "text": "東京・水道橋の店では……", "face": "point", "react": "surprise" } ] } ]
```

- `characters` のキーは `voices` のキーと同じにする。`order` は左から右の並び。
- `face` は話し手の表情、`react` は聞き手の表情。省略すると `normal`（前のセリフで `trouble` や `surprise` などを付けたキャラがそのまま残らないよう、戻したいセリフでは明示的に `normal` を指定する）。
- 書き出しの最初に、全セリフの `face` と `react` の立ち絵があるかを確かめ、無ければ止まる。
- 口の開け閉めは、セリフの声の大きさを 1 秒 30 回測った値 (最大を 1 として 0.15 より大きい所で開く)。
- 高さ 300 では、右側に置いたグラフや写真パネルの下端と重なった (もやし特集、1920x1080)。240 なら重ならない。右側の重ね物は y 680 までに収める。
