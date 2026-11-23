# 引き継ぎメモ (2026-11-21 時点)

README.md は 11/20 夜の `v1.0.0` までしか書いていない。このメモは 11/21 の作業を含めた現状と、次に決めることをまとめる。README を書き直すときにこの内容を移し、このメモは消してよい。

## 1. 作品の趣旨

- 昼は人であふれる渋谷スクランブル交差点とセンター街を、誰もいない真夜中に、人の目の高さ・歩く速さ (1.15 m/s) で一人称で歩く。Backrooms 的なリミナルスペースの環境動画。
- 解説動画ではない。ナレーション、字幕、立ち絵は使わない (`characters/`, `shots/example.json`, `narrated.json`, `photo_swap.json` はテンプレートの残り)。音は Vaporwave (Mallsoft / Slushwave) の BGM だけ。
- このリポジトリでの意味: 映像生成 AI で作る「無人の渋谷」とは違い、PLATEAU と地理院タイルの実際の形と位置から、ショット JSON で何度でも同じ映像を書き出せること。

## 2. これまでの流れ

| 時期 | 版・出力 | 内容 |
|---|---|---|
| 11/20 17:43〜21:33 | v0.1.2〜v0.1.6 → `episode-v1.0.0` | 3 章 95.45 秒の歩行動画を完成。PLATEAU 建物の超解像、SDXL で路面を夜にした変換、横断歩道の決定論的描画、BGM 合成、VHS 風の色調。 |
| 11/20 18:29〜18:43 | `out/prototype_refs/proto_*.png` | 目標とする見た目の静止画 (無人でネオンが光る交差点)。**作った手順のスクリプトがなく、出どころが不明。** |
| 11/21 09:20 | `wan22_i2v_test` | proto の静止画を Wan2.2 で動画にする実験。 |
| 11/21 09:29〜09:44 | `cinemagraph_5s/10s`, `cctv_cam0*` | proto の静止画から、カメラ固定の繰り返し動画 (看板だけが動く、監視カメラ風) を作る実験。 |
| 11/21 10:21〜10:52 | `comfy_repro`, `comfy_repro_v2` | 3D の配置 (canny) と参考写真から、ComfyUI で proto に近い静止画を作り直す実験。 |
| 11/21 11:18〜15:22 | `shibuya-comfy-materials-v12`, `shibuya-comfy-billboards-v13〜v31` | **3D の路線に戻り**、交差点の 1 カット (4 秒) を proto に近づける作業。壁面アトラス、写真から切り抜いた看板 (8→30 枚)、街灯・信号・アーチ (12 個)、Three.js の平面路面、fov 58→82。 |

直近の比較画像: `flyover/out/shibuya-comfy-billboards-v31/compare_v31_vs_proto.png` (上が v30/v31、下が proto と参考写真)。

## 3. v31 と目標の差 (比較画像から読めること)

- 看板の位置と種類は、proto の構図にかなり近い。
- 画面の下半分を暗いアスファルトが占めている。視点が低く、pitch 84・fov 82 のため手前の地面が広く写る。横断歩道の白線は遠くにかすかに見えるだけで、proto のように手前から奥へ伸びていない。
- 建物の低層階 (スターバックス、TSUTAYA の店先など) が光っていない。濡れた路面へのネオンの映り込みもない。
- 建物の上層は窓の点が並ぶだけの暗い箱に見える。

## 4. 未コミットのレンダラー拡張への依存

v31 は、未コミットの `packages/renderer` の変更がないと描けない。使っている項目は `fov`, `plateauBuildings.groundPlane`, `facadeTextures` (`atlas`, `idVariants`), `streetProps`, `billboards` の 5 つ。

- 描画本体は `packages/renderer/src/page/plateau-street-scene.ts` (新規、テストなし)。
- `episode-v1.0.0` の 3 章はこれらを使っていない (地面は `overlays` の image)。

## 5. 未解決の問題

1. **proto 画像の出どころ**: 生成スクリプトがない。実写真か、外部の画像生成で作ったものかを記録する必要がある。
2. **看板の権利**: `assets/billboards/` は CC BY などの写真から広告を切り抜いたもの。写真のライセンスは商用・改変可でも、写っている広告には商標や人物 (タレントの写真) が含まれる。公開の前に扱いを決める。
3. **出典の記録が古い**: `credits.json` には 11/21 に追加した素材 (夜景写真 222 枚の manifest、切り抜いた看板、ComfyUI で作った外壁や素材) が入っていない。
4. **ComfyUI への依存**: 多くのスクリプトが `http://127.0.0.1:8188` のローカル ComfyUI を前提にしている。使ったモデルとワークフローを記録しないと再現できない。
5. **スクリプトの整理**: 試作 (`test_wan22_i2v.py`, `generate_cinemagraph_*`, `generate_cctv_loops.py`, `comfy_generate_base_stills*.py`) と本番の工程が同じ場所に混ざっている。
