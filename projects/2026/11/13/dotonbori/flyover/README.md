# 道頓堀からコスモスクエアへ

新しい動画版は版番号付きのファイル名で書き出し、既存の版は上書きしない。

制作者 (yuiseki) が撮影した写真のクレジットは `写真：yuiseki` と表記する。

YuisekinTV の特集動画です。`geo-video-renderer` のテンプレート (旧名 gsi-terrain-flyover) を基に、ずんだもんと四国めたんの掛け合いを、地理院の地図・年代別空中写真、写真、浮世絵に重ねます。

- 原稿：`../道頓堀文化の空洞化_ずんだもん四国めたん台本.md`
- 映像用ショット：`shots/dotonbori.json`。`build_story.py` が原稿から作成します。
- 地図と古い空中写真：`assets/maps/`。元データと範囲、出典は `assets/maps/README.md` と `assets/maps/manifest.json`。
- 写真・浮世絵：`assets/commons/`。作者・ライセンス・出典URLは `credits.json`。
- 音声：VOICEVOX Engine。ずんだもん style 3、四国めたん style 2。
- 概要欄：`description.txt`。資料、地図、音声、立ち絵、写真の出典を含みます。

このディレクトリで `npm install` と `npx playwright install chromium-headless-shell` を実行してから書き出す。画像 (写真、地図、立ち絵) はリポジトリに含めていないので、`credits.json` と `assets/maps/manifest.json` の出典から取り直す。書き出しには Node.js、Chromium、ffmpeg、日本語フォントと VOICEVOX Engine が必要です。

## 再生成

このディレクトリで、ホストの資源制限ルールに従ってメモリと CPU に上限を掛けて流す。

```bash
node ../../../../packages/renderer/dist/src/render.js shots/dotonbori.json --project . --out out/新しい出力名 --size 1920x1080 --fps 24
```

既存フレームを消さないため、出力先に `frames/` があるとレンダラーは停止します。毎回、新しい出力先を指定してください。地理院タイルへの負荷と計算資源に注意し、章単位の書き出しは最大3並列で実行します。

画と声を確認する短い試写は `shots/voice-preview.json` から作れます。`--stills 45 --no-voice` は全体の構図を間引いて確認するための設定です。文字の読み方はショットの `speech` に指定します。

章別レンダリングは、作業全体を一つの資源制限スコープで囲みます。指定した出力先は新規作成され、既存の出力は上書きしません。章ごとに無音のタイトルカードを挿入し、結合後の全音声を同じ基準で正規化します。

```bash
python3 ../../../../packages/pipeline/video/chapter_pipeline.py chapters.json --out out/新しい出力名 --workers 3
```

## 地名表示の試作

ショット JSON のトップレベルに `"osmLabels": true` を指定すると、`tile.yuiseki.net` の OpenMapTiles を使用し、空中写真の上に市区・島・河川・鉄道関連の日本語名を表示します。文字の日本語名がない場合は通常名にフォールバックします。表示が密になりすぎないよう、町丁目は表示対象から外しています。主題となる地点はショットの `label` に座標を指定して補えます。

`shots/labels-preview.json` は道頓堀・コスモスクエア・両国などを示す静止画試作用です。`out/labels-preview-v3/frames/00001.jpg` および `00003.jpg` に例があります。この設定は既存の完成動画には適用されていません。

地名は OpenStreetMap の現代のデータです。古い空中写真に重ねる場合は、その時代の地名や施設の存在を示すものではないことを画面に明記してください。動画の画面と概要欄には OpenStreetMap contributors と OpenMapTiles の出典を記載します。局所的な位置指定には `nominatim.yuiseki.net` の検索結果を使えます。候補の `importance` と `place_rank`、種別、範囲を併用し、主題の地名は重要度だけで除外しないようにします。`assets/nominatim-label-candidates.json` は範囲を限定した候補の記録です。Nominatim の importance がタイル内の各地名に自動的に付くわけではありません。

鉄道の実線形は `overpass.yuiseki.net` で路線 relation から取得できます。ニュートラムは `route=light_rail` の relation 444913 / 9603948 として取得できました。Overpass には 2025 年 9 月時点のデータが返ることを確認しており、利用時には更新時刻を再確認します。`valhalla.yuiseki.net` は徒歩経路の応答を確認しました。徒歩の計算結果を鉄道経路として使用しないでください。

## 章のつなぎ（v0.1.6）

`add_transitions.py` は保存した v0.1.5 の台本とショットから、各章末の掛け合いと地理的な移動を追加します。大阪と東京の間は、広域に引いて移動してから目的地に寄ります。`shots/dotonbori.json` はこれらの移動を含む完成ショットです。章末の移動に大阪の駅ラベルが不適切に追加されないよう、`transition` 属性で判別します。

章の一部だけを修正した場合は `--reuse-from out/前の出力名` を指定できます。章ごとのショット仕様が完全に一致する章だけを再利用し、異なる章は再描画してから結合します。素材ファイルやレンダラーの内容が変わった場合は、仕様が同じでも再利用せず全章を再描画してください。

## 移動速度と地名表示（v0.1.7）

`soften_transitions.py` は v0.1.6 の台詞を維持し、遠距離や章間の移動を長くして、`smooth` 補間で加減速を抑えます。コスモスクエア駅と大阪南港のラベルは、それぞれ駅と地域を表す位置に配置します。共通レンダラー (`packages/renderer/src/lib.ts`) の `smooth` は従来の補間を選んだショットには影響しません。

## 似た写真の重複 (v0.1.2)

v0.1.2 は、同じ場所で続けて撮った見た目のほぼ同じ写真を、別の写真として両方使っている (たこ焼きの 2 枚 `012c98f4…` と `ccfeb704…` は 9 秒差、看板のビルの 2 枚 `46d8534a…` と `9e289c21…` は 1 分差)。「同じ写真を繰り返し使わない」を画像ファイルの同一性で判定した読み違いで、v0.1.3 以降はそれぞれ 1 枚だけを使っている。判定の仕方は `geo-video-production` の `production-workflow.md`。
