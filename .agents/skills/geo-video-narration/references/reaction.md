# リアクションワイプ (話し手の立ち絵を隅に出す)

画面の右下 (字幕の帯の上) に、2 人の話し手の立ち絵を並べる。

- 話している側: 明るく、少し大きい。声の大きい所で口が開く。セリフの頭で少し跳ねる。表情はセリフの `face`。
- 聞いている側: 暗くして少し小さい。表情はセリフの `react`。
- 2 人とも、別々の間合いでまばたきする (時刻だけで決まるので、同じコマは何度書き出しても同じ)。
- 出ているあいだ、右下の出典は左下へ移る。

手本: 図解中心の地図解説動画で、右下に出続けるキャラクター (場面ごとに驚く、本を読む、両手を上げる)。用語は [graphics.md](../../geo-video-visuals/references/graphics.md) の「リアクションワイプ」。

## 素材の選択肢（キャラ別リファレンス）

レンダラーが読み込む形式は `<project>/assets/chara/<名前>/<表情>_<目 o|c>_<口 o|c>.png` で共通のため、以下のいずれの形式でもキャラクターを追加・切り替えできる。

- **ずんだもん・四国めたん（PSD 立ち絵 + VOICEVOX）**: [zunda-metan.md](zunda-metan.md)（`packages/pipeline/narration/psd_sprites.py` で書き出し）
- **ゆっくり霊夢・魔理沙（PNG パーツ立ち絵 + Open JTalk 等）**: [yukkuri.md](yukkuri.md)（`packages/pipeline/narration/part_sprites.py` で書き出し）
- **既存 PNG 差分や簡易合成素材の直接配置**: すでに切り出し済みの立ち絵 PNG を使う場合は、`<表情>_<o|c>_<o|c>.png` のファイル名で `assets/chara/<名前>/` へ配置すればそのまま利用できる。

いずれの形式でも、`sheet.png` を目で見て「目を閉じた差分が実際に閉じているか」「表情と顔位置が揃っているか」を確認する。

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
