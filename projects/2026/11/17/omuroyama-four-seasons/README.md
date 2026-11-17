# 大室山の四季

地理院の空中写真と標高タイルで大室山を描き、既存の季節画像をクロスフェードする32秒の無音映像です。季節画像は地理院空中写真に Copernicus Sentinel-2 L2A（2023〜2024年）の色を転写したもので、実写の連続映像ではありません。

山の形と色の変化を見やすくするため、山を中心に保ち、方位を32秒で60度だけ滑らかに変えます。ズームと傾きは固定しています。

リポジトリのルートから、既存の素材を参照して再生成できます。

```bash
systemd-run --user --scope -q -p MemoryMax=8G -p MemorySwapMax=0 -p CPUQuota=400% -- \
  node packages/renderer/dist/src/render.js projects/2026/11/17/omuroyama-four-seasons/shots/omuroyama-four-seasons-v0.1.0.json \
  --project packages/renderer/test/fixtures \
  --out projects/2026/11/17/omuroyama-four-seasons/out/omuroyama-four-seasons-v0.1.0 --no-voice
```

事前に renderer のビルドが必要です。素材は `packages/renderer/test/fixtures/omuro-seasons/` を参照します。
