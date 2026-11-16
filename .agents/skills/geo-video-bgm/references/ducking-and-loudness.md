# FFmpeg による自動ダッキングと音量マスタリング

声のトラック（VOICEVOX）をトリガーにして BGM の音量を自動で下げ（サイドチェイン・コンプレッション）、最終的に YouTube 向けの基準ラウドネスへ揃える手順。

## 基本構成（`sidechaincompress` + `loudnorm`）

レンダラーの単発ショットにある `bgm` 指定は音量一定だが、完成動画（または音声トラック結合後）に対して FFmpeg の `sidechaincompress` を使うと、発話中だけ BGM を自動で抑えられる。

```bash
ffmpeg -y -i episode_voice_only.mp4 -stream_loop -1 -i bgm.wav \
  -filter_complex "\
[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.35[m];\
[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v1][v2];\
[m][v2]sidechaincompress=threshold=0.04:ratio=8:attack=15:release=350[mc];\
[mc][v1]amix=inputs=2:weights=1 1:normalize=0[s];\
[s]loudnorm=I=-14:TP=-1.5:LRA=11[out]" \
  -map 0:v -map "[out]" -c:v copy -c:a aac -b:a 192k -shortest episode_with_bgm.mp4
```

### パラメータの調整目安

| パラメータ | 目安値 | 役割 |
|---|---|---|
| `volume` (BGM 入力) | `0.25` 〜 `0.40` | ダッキング前の基準音量。解説主体の場合は控えめに置く |
| `threshold` | `0.03` 〜 `0.05` | どの程度の声の大きさでダッキングを発動するか |
| `ratio` | `6` 〜 `10` | 発話中の BGM の下げ幅。大きいほど声が明瞭になる |
| `attack` | `15` ms | 話し始めに BGM が下がる速さ |
| `release` | `300` 〜 `400` ms | 話し終わりに BGM が戻る速さ。短すぎると息継ぎのたびに上下して耳障りになる |
| `loudnorm` | `I=-14:TP=-1.5:LRA=11` | YouTube 等の配信環境に合わせた統合ラウドネス基準 |

## 確認手順

1. **無音章カード・冒頭の確認**: `-stream_loop -1` でループさせた継ぎ目にクリックノイズがないか確認する。
2. **フェードアウト**: 動画の末尾 2〜3 秒は `afade=t=out:st=<終了秒-2>:d=2` を BGM 側に掛け、ぶつ切りを防ぐ。
3. **聴感確認**: 必ず完成 MP4 を通常速度で再生し、語尾が BGM に飲まれていないか、息継ぎで BGM が上下しすぎていないかを確認する。
