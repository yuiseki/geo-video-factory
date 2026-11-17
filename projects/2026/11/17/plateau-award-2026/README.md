# 空撮は、書ける。 — PLATEAU AWARD 2026 応募作品

`geo-video-factory` を用いて制作した、国土交通省 PLATEAU と国土地理院タイル・OpenStreetMap・衛星データ（Copernicus Sentinel-2）・AIエージェントによる地理3D映像作品（176秒 / 1920×1080 / 30fps）。

## 構造と再レンダリング設計

各Scene（`S01`〜`S10`）とBridge（`B01`〜`B07`）は、映像（`map` レイヤー）、テロップ・ラベル（`overlay` レイヤー）、音声（`audio`）を独立して差し替え・再生成できるよう分離されています。

- `manifest.json`: 全17クリップのID、尺、入口・出口カメラ契約（`center`, `zoom`, `pitch`, `bearing`）、データ・レイヤー、テロップ、出典の正本
- `generate_shots.py`: `shots/<ID>.json` を生成し、隣接クリップ間のカメラ境界一致を検証
- `prepare.py`: 既存プロジェクト／E2Eキャッシュへのシンボリックリンクを設定
- `render_clip.py`: 指定クリップのみを `map` / `overlay` レイヤー別にレンダリング
- `compose_overlays.py`: `S08`（AI制作フロー表示）の追加透過オーバーレイ動画を生成
- `compose_audio.py`: VOICEVOX ナレーション、176秒 BGM、効果音を合成し、`sidechaincompress` ダッキングと `-14 LUFS` 音量マスタリングを実施
- `build_final.py`: 全17クリップを `manifest.json` 順に結合し、最終 MP4 を生成

## 再生成手順

```bash
# 1. レンダラーのビルド（初回）
cd packages/renderer && npm install && npm run build && cd ../..

# 2. 3Dデータ・素材準備（初回のみ函館・大阪の prepare.py を実行）
OVERPASS_URL=https://overpass.yuiseki.net/api/interpreter .venv/bin/python projects/2026/11/17/hakodate-terrain-buildings/prepare.py
OVERPASS_URL=https://overpass.yuiseki.net/api/interpreter .venv/bin/python projects/2026/11/17/tour-shisaibashi-dotonbori-cosmosqare/prepare.py
.venv/bin/python projects/2026/11/17/plateau-award-2026/prepare.py

# 3. ショットJSON生成・検証、音声・追加オーバーレイ生成
.venv/bin/python projects/2026/11/17/plateau-award-2026/generate_shots.py
.venv/bin/python projects/2026/11/17/plateau-award-2026/compose_audio.py
.venv/bin/python projects/2026/11/17/plateau-award-2026/compose_overlays.py

# 4. 本番レンダリング（個別差し替え例: .venv/bin/python .../render_clip.py S04 --mode final）
.venv/bin/python projects/2026/11/17/plateau-award-2026/render_clip.py --mode final

# 5. 最終結合
.venv/bin/python projects/2026/11/17/plateau-award-2026/build_final.py --mode final --version v1.0.0
```

## 出典・クレジット

- 建物3D都市モデル：国土交通省 PLATEAU（東京都23区・新宿区・福生市・大阪市）
- 空中写真・標高・建物外形：国土地理院 地理院タイル（全国最新写真シームレス・標高タイル・最適化ベクトルタイル）を加工
- 建物属性・地名：© OpenStreetMap contributors（ODbL）
- 衛星季節色度：Copernicus Sentinel-2 L2A（2023–2024年）
- 地球広域背景：NASA Blue Marble
- 音声：VOICEVOX:四国めたん
- BGM・効果音：ローカル合成（ライセンスクリーン）

建物の高さ、屋根形状、外壁・窓の模様には推定を含みます（実測・防災判断用ではありません）。函館（`S09`）は国土地理院の建物外形・標高・空中写真と OpenStreetMap 属性を使用しており、PLATEAU による高さ較正は行っていません。
