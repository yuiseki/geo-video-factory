# Backrooms × Vaporwave リミナルスペース動画（渋谷スクランブル交差点〜センター街）

昼間は人でごった返している渋谷スクランブル交差点と渋谷センター街を、**誰もいない真夜中・人間の一人称視点（歩行速度 1.15 m/s ≒ 時速 4.1 km）** で静かに彷徨い、Mallsoft / Slushwave 風の Vaporwave BGM が流れ続ける環境動画プロジェクトです。

## 完成版（`v1.0.0`）

- **出力動画**: `flyover/out/episode-v1.0.0/shibuya-backrooms-vaporwave-v1.0.0.mp4`（95.45 秒 / 1280×720 / 24fps / -14.0 LUFS）
- **構成（3 チャプター・0.8 秒クロスフェード結合）**:
  1. `ch01_crossing.json`（31.3 秒 / 36.0 m）: スクランブル交差点の横断歩道を渡り、QFRONT と大盛堂書店の間のセンター街入口へ進む
  2. `ch02_centergai_mid.json`（31.1 秒 / 35.8 m）: 無人の深夜のセンター街の路地を西へ歩く
  3. `ch03_centergai_deep.json`（34.6 秒 / 39.8 m）: センター街の奥を歩き、途中でゆっくり左右を見回しながら暗闇へフェードアウト

## 技術構成

- **3D 建物**: 国土交通省 PLATEAU（渋谷区 2025 LOD2 テクスチャ付き・73 タイル）を取得し、内蔵テクスチャ 62 タイルを `RealESRGAN_x4plus`（BSD-3-Clause）で 4 倍超解像（最大 `4096px`）。レンダラーの `night` ライティングと深い紫〜紺の霧（`sky`）で深夜の空間を構築。
- **路面テクスチャ**: 地理院シームレス写真（zoom 18）の渋谷狭域を `SDXL Base 1.0`（Open RAIL++-M）+ `xinsir/controlnet-tile-sdxl-1.0`（Apache 2.0）で車・人の影のない暗い夜間路面へ変換後、`RealESRGAN_x4plus` で `5120×3584` へ超解像し、実測座標に基づく 5 本の横断歩道・センター街舗装・ネオン反射・アスファルト粒子を決定論的に重畳。
- **BGM**: `flyover/scripts/generate_vaporwave_bgm.py` でローカル合成した Mallsoft / Slushwave 風 24 秒シームレスループ（A4=432Hz チューニング、ワウフラッター、マルチタップリバーブ、蛍光灯 60Hz/120Hz ハム音）を `-14 LUFS` 基準でマスタリング。
- **仕上げ**: FFmpeg による VHS/Vaporwave 色調（微細な色収差 `rgbashift`、パープル〜ブルー系 `colorbalance`、`vignette`、フィルムグレイン `noise`）。

## ディレクトリ構成

- `README.md`: 本ドキュメント
- `credits.json`: 使用データ・素材・モデル・ライセンスの出典記録
- `research/`: Overpass API によるセンター街中心線座標（`centergai_overpass.json`）、参考写真メタデータ（`photos_manifest.json`）
- `flyover/scripts/`:
  - `prepare_shibuya.py`: PLATEAU 3D Tiles 取得・キャッシュ
  - `upscale_shibuya_assets.py`: 地理院タイル結合＋`RealESRGAN_x4plus` 一括超解像
  - `refine_crossing_ground.py`: ComfyUI API 経由の狭域路面 SDXL + ControlNet Tile 変換
  - `overlay_procedural_crosswalk.py`: 横断歩道・センター街舗装・ネオン反射の決定論的描画
  - `generate_vaporwave_bgm.py`: Mallsoft / Slushwave 風 BGM ローカル合成
  - `build_walk_shot.py` / `build_episode.py`: 等速歩行（1.15 m/s）ショット JSON 生成
  - `collect_shibuya_photos.py`: 改変可・商用可の渋谷写真収集（143 枚）
- `flyover/shots/episode-v1.0.0/`: 本番 3 チャプターのショット JSON

## 出典・権利管理

詳細は [credits.json](credits.json) および [research/photos_manifest.json](research/photos_manifest.json) を参照してください。画像・動画・音声・GLB ファイルは `.gitignore` により Git 管理対象外です。

画像生成モデルのライセンスと、このプロジェクトの立場 (作者が求めるクレジット表記を受け入れる、モデルを販売も配布もしない) は [research/generation_model_licences.md](research/generation_model_licences.md) にあります。
