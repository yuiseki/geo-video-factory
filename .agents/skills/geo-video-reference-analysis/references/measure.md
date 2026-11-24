# 測る

スクリプトは `scripts/` にある。どれも 1 本の動画を読むので、資源の上限を掛けて流す。1080p で 20 分の動画なら、`media.py` が 4 分前後、`motion.py` が 3 分前後、`look_changes.py` が 1〜2 分かかった (CPU 4 コア相当の上限で)。

```bash
S=<skill-dir>/scripts; D=<保管庫>/<ID>
python3 $S/refstats.py $D/<ID>.info.json
python3 $S/transcript.py $D/<ID>.ja.vtt --duration <秒> --out $D/transcript.txt
python3 $S/media.py $D/<ID>.mp4 $D --info $D/<ID>.info.json
python3 $S/look_changes.py $D/<ID>.mp4
uv run --with opencv-python-headless --with numpy python $S/motion.py $D/<ID>.mp4 $D/motion.tsv
python3 $S/shot_plan.py --cuts $D/cuts.txt --motion $D/motion.tsv --transcript $D/transcript.txt --info $D/<ID>.info.json --out $D/SHOT_PLAN.md
```

テストは `python3 scripts/tests/test_scripts.py`。

## 何を測るか

| 測るもの | スクリプト | 読み方 |
|---|---|---|
| 公開の数字 | `refstats.py` | 登録者あたりの再生、高評価率、コメント率、1 日あたりの再生、章の数と平均の長さ ([metrics.md](metrics.md)) |
| 話す速さ | `transcript.py` | 字幕の文字数を動画全体の長さで割る (無音も含む)。動画どうしを同じ物差しで比べるため。話している間だけの速さは、無音を除いた時間で割る |
| 画面の切り替わり | `media.py` → `cuts.txt` | ffmpeg の scene が 0.25 を超えた時刻。カットの数と間隔。溶ける切り替え (ディゾルブ) は数に入りにくい |
| 音量と無音 | `media.py` → `loudness.txt` | 統合ラウドネス (LUFS) とラウドネスレンジ。-50 dB 以下が 0.5 秒以上続く無音の数は、BGM が敷かれ続けているかの目安 (BGM があると 0 に近い) |
| コマの一覧 | `media.py` → `sheets/` | 20 秒おきのコマを 4x4 に並べ、上部の黒帯に時刻 (映像を隠さない)。展開の速い動画は `--sheet-step 10`。変化点を重点抽出する場合は `--adaptive --budget 32` で `adaptive/storyboard.jpg` と `adaptive/timeline.txt` を出力 |
| 局所の動き・文字 | `packages/pipeline/video_inspect.py` (`zoom` / `frame`) | 注目区間を `zoom --start <t1> --end <t2>` で連続フレーム展開し、細かい文字や図解は `frame --t <t> --crop x,y,w,h` で原寸確認する |
| 章の頭 | `media.py` → `chapters/all.jpg` | チャプターごとに開始の 0.5、1.5、3 秒後のコマを 1 行に。区切りの絵の作りが並べて見える |
| 見た目の変化 | `look_changes.py` | 明るさか色の濃さが 2 秒で大きく変わった回数 (1 分あたり) と、同じ見た目が続いた最長の秒数 |
| カメラと写真の動き | `motion.py` | 0.5 秒ごとに寄る、引く、上下左右、止まっている、カットを判定し、時間の割合と速さの中央値を出す |
| ショット分解雛形 | `shot_plan.py` → `SHOT_PLAN.md` | `cuts.txt`、`motion.tsv`、`transcript.txt`、`info.json` を結合し、4 層構造のショット一覧・統計・再現プラン雛形を生成する ([shot-deconstruction.md](shot-deconstruction.md)) |

## 測り方の限界

- `motion.py`: 速さは少し小さく出る (0.8〜0.9%/秒の寄りが 0.65〜0.8%/秒)。画面に止まった大きな重ね物 (キャラクター、大きな文字) があると、そちらに引っ張られて「止まっている」と出る。平らな図解とキャラクターの多い動画は、実際より動きが少なく出る。
- `look_changes.py`: 明るさと色しか見ていない。見た目の変化が多くても、どの場面も同じ組み立てなら単調に感じる。コマの一覧と並べて読む。
- 写真の場面だけの動きを知りたいときは、コマごとに写真かどうかを判定して突き合わせる。手元の画像言語モデルに 2 秒おきのコマを聞く方法が使えるが、十数枚を目で確かめて判定が合っていることを先に確かめる。
- 自動字幕の文字数は、固有名詞や数字の誤認識で増減する。速さの比べは 0.5 字/秒くらいの差を誤差と見る。

## 拡張ツール候補（精密計測が必要なとき）

標準スクリプト（`media.py` / `transcript.py`）で捉えきれない音響や発話のタイミングを測る場合、次の Python ライブラリを組み合わせる。

- **`librosa`（音響・ビート解析）**: BGM の BPM（テンポ）、拍位置（`beat_track`）、音の立ち上がり（`onset_detect`）を抽出し、参考動画の「音ハメ」（カットや画面変化が拍・効果音とどれだけ一致しているか）を定量化する。自前動画のカット点・カメラキーを音楽に合わせる設計にも応用できる。
- **`WhisperX`（日本語対応の強制アライメント）**: `.ja.vtt` が取得できない動画や、自動字幕の時刻ずれが大きい動画に対して、音声から単語・文節レベルの正確な発話区間タイムスタンプを生成し、無音区間を除いた実発話速度や字幕同期のズレを検証する。
