# FFmpeg による自動ダッキングと音量マスタリング

声のトラック（VOICEVOX）をトリガーにして BGM の音量を自動で下げ（サイドチェイン・コンプレッション）、最終的に YouTube 向けの基準ラウドネスへ揃える手順。

## 原則：生コマンドではなく型付きヘルパーを使う

エージェントが生の `ffmpeg` コマンド文字列を組み立てると、入力ファイルの上書き・`-pix_fmt` やサンプルレートの欠落・フィルタ構文ミスが起きやすい。必ず `packages/pipeline/video/ffmpeg_ops.py` と `packages/pipeline/video/video_qa.py` を通して **事前プローブ → 編集（ドライラン確認） → 事後検品** の順で処理する。

- 出力先ガード：入力と同じパスへの上書きを拒否し、既存出力ファイルも `--overwrite` 明示なしでは上書きしない。
- ロスレス優先：映像の再エンコードが不要な操作（ダッキング・2-pass 正規化・トリム・結合）は既定で `-c:v copy`（ストリームコピー）を使う。
- `--dry-run --json`：実処理の前に生成される FFmpeg 引数配列を確認できる。

### 1. 事前プローブ（尺・ストリーム確認）

末尾フェードアウト開始秒（`duration - 2` など）と音声ストリームの有無を先に確認する。

```bash
python3 packages/pipeline/video/ffmpeg_ops.py probe episode_voice_only.mp4 --json
```

### 2. BGM ダッキング合成（`duck-bgm`）

`sidechaincompress` + `amix` + `loudnorm` を型付き引数で組み立てる。まず `--dry-run --json` でコマンドを確認してから実行する。

```bash
python3 packages/pipeline/video/ffmpeg_ops.py duck-bgm \
  episode_voice_only.mp4 bgm.wav \
  -o episode_with_bgm_v0.1.0.mp4 \
  --volume 0.35 --threshold 0.04 --ratio 8 \
  --fade-out-start 118 --fade-out-duration 2 \
  --dry-run --json
```

### 3. 2-pass ラウドネス正規化（`loudnorm`）

単発の 1-pass `loudnorm` より精度の高い EBU R128 2-pass 正規化を適用したい場合（BGM なし音声のみ、または最終仕上げ）は `loudnorm` サブコマンドを使う。映像は `-c:v copy` のまま音声のみ `linear=true` で正規化する。

```bash
python3 packages/pipeline/video/ffmpeg_ops.py loudnorm \
  episode_with_bgm_v0.1.0.mp4 \
  -o episode_master_v0.1.0.mp4 \
  -I -14 --tp -1.5 --lra 11
```

### 4. 事後検品（`video_qa.py`）

書き出し後は `video_qa.py` でラウドネス（`-14 LUFS +/- 2`、トゥルーピーク `-1.0 dBTP` 以下）、無音・黒画面・フリーズ異常、必要ならコンタクトシートを確認する。

```bash
python3 packages/pipeline/video/video_qa.py episode_master_v0.1.0.mp4 \
  --platform youtube --content --json
```

## 内部フィルタ構成の参考（`sidechaincompress` + `loudnorm`）

`ffmpeg_ops.py duck-bgm` が生成するフィルタグラフの等価構成は次の通り。

```bash
ffmpeg -hide_banner -nostdin -n -i episode_voice_only.mp4 -stream_loop -1 -i bgm.wav \
  -filter_complex "\
[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.35[m];\
[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v1][v2];\
[m][v2]sidechaincompress=threshold=0.04:ratio=8:attack=15:release=350[mc];\
[mc][v1]amix=inputs=2:weights=1 1:normalize=0[s];\
[s]loudnorm=I=-14:TP=-1.5:LRA=11[out]" \
  -map 0:v -map "[out]" -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart episode_with_bgm.mp4
```

### パラメータの調整目安

| パラメータ | 目安値 | 役割 |
|---|---|---|
| `--volume` (BGM 入力) | `0.25` 〜 `0.40` | ダッキング前の基準音量。解説主体の場合は控えめに置く |
| `--threshold` | `0.03` 〜 `0.05` | どの程度の声の大きさでダッキングを発動するか |
| `--ratio` | `6` 〜 `10` | 発話中の BGM の下げ幅。大きいほど声が明瞭になる |
| `attack` | `15` ms | 話し始めに BGM が下がる速さ |
| `release` | `300` 〜 `400` ms | 話し終わりに BGM が戻る速さ。短すぎると息継ぎのたびに上下して耳障りになる |
| `loudnorm` | `I=-14:TP=-1.5:LRA=11` | YouTube 等の配信環境に合わせた統合ラウドネス基準 |

## 確認手順

1. **無音章カード・冒頭の確認**: `-stream_loop -1` でループさせた継ぎ目にクリックノイズがないか確認する。
2. **フェードアウト**: 事前プローブで得た尺から末尾 2〜3 秒に `--fade-out-start` / `--fade-out-duration` を指定し、ぶつ切りを防ぐ。
3. **数値検品＋聴感確認**: `video_qa.py` で LUFS / TP / 無音異常が PASS であることを確認したうえで、必ず完成 MP4 を通常速度で再生し、語尾が BGM に飲まれていないか、息継ぎで BGM が上下しすぎていないかを確認する。
