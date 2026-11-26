# PLATEAU++ v0.1.0

PLATEAU++ (`packages/pipeline/buildings/plateau_pp.py`) の最初の版を定めるプロジェクトです。
建物の見た目を GLB そのものに焼き込み、ブラウザのレンダラーでも Blender でも、glTF の標準の範囲だけで同じに見えるようにします。

## なぜ焼き込むのか

今の PLATEAU++ は、テクスチャの無い建物の見た目を manifest の値 (`facade_colors`、`roof_texture`) で渡し、描画系がシェーダーで解釈しています。
描画系が増えるたびに同じ解釈を書き写すことになり、ずれが生じます。
実際に、Blender の `pp_scene.py` はこの解釈を持たず、テクスチャの無い PLATEAU の建物を一律の灰色で描いています。

## v0.1.0 の範囲

1. 取得: PLATEAU から取ったままのタイルと地理院タイルは、共有キャッシュ (`$GEO_VIDEO_CACHE`、既定は `tmp/.cache/` の `plateau-raw/` と `gsi/`) から読む。
2. 実在しえない建物を外す: `buildings/plausibility.py`。
3. 焼き込み:
   - テクスチャの無い PLATEAU の建物は、上向きの面を屋根のプリミティブに分け、地理院の写真 (z18) をタイルの範囲で切り出して埋め込み、真上から投影した UV を付ける。
   - 残りの面は壁のプリミティブにし、ID と高さで決まる色 (`city_proxy.wall_hex`) を頂点色 (COLOR_0) で持たせる。
   - 元のテクスチャを持つ面には手を付けない。
   - 補完の建物 (city_proxy) も同じ形にそろえ、描画系のシェーダーが読む独自の頂点属性に頼らない。
4. PLATEAU のタイルが無い範囲でも、地理院の建物外形からの補完だけで作る。
5. 置き場: 完成品は `tmp/.cache/plateau-pp/v0.1.0/<tileset・範囲・seed・テクスチャ寸法のハッシュ>/` に作る (`plateau_pp` を出力先なしで流す)。見た目が変わる修正をしたら `PLATEAU_PP_VERSION` を上げる。ディレクトリで版を分けるのは、このキャッシュだけ。

1〜5 は `plateau_pp` に入った。焼き込んだ GLB は `asset.extras.plateau_pp_bake` に版を持ち、ブラウザのレンダラーはそれを見て、描画時の補正を重ねずにそのまま描く。描画系に残る約束は、上向きの面がアルベドをそのまま返す照明と、夜に `pp-wall-*` の `emissiveFactor` を上げることの 2 つ。

## 試す範囲

`areas.json` に範囲を置いています。`OVERPASS_URL=<自前の Overpass> python projects/2026/11/26/plateau-pp/build_trial.py` で、各範囲の PLATEAU++ を `out/<名前>/` に作り直します (ホストの資源制限に従って実行する)。`out/` は使い捨てで、版はコミットが持ちます。

| 名前 | 場所 | 選んだ理由 |
|---|---|---|
| shinjuku | 西新宿 5 丁目 | PLATEAU のモデルがあり、テクスチャ付きと無しが混ざる |
| fussa | 福生駅 | PLATEAU のモデルはあるが、ほとんどにテクスチャが無い |
| hamura | 羽村駅 | PLATEAU のタイルが無い |

## 確かめ方

焼き込んだ同じ GLB を、ブラウザ (three.js の素の `GLTFLoader`、独自シェーダーなし) と Blender (glTF の読み込みだけ) で同じカメラから描き、並べて比べます。

```sh
OVERPASS_URL=<自前の Overpass> PYTHON=<packages/pipeline の依存が入った python> projects/2026/11/26/plateau-pp/compare_trial.sh
```

リポジトリのルートから流します。`build_trial.py` で PLATEAU++ を作り、`scene_trial.py` で `out/<名前>/scene.json` を書き、`compare_blender.py` と `compare_three.mjs` で描いて、`compare_sheet.py` が `out/compare/sheet.jpg` にまとめます。

本番のレンダラー (flyover) での新旧の比較は、`build_trial.py --no-bake` で旧 PLATEAU++ を `out/before/<名前>/` に作ってから `compare_flyover.py` を流します。同じカメラの俯瞰と近景を描き、`out/compare/flyover_overview.jpg` と `flyover_close.jpg` に、左に旧、右に v0.1.0 を並べます。

タイルの置き方 (PLATEAU の RTC から局所座標への行列)、地面の高さ、カメラは `scene_trial.py` が一度だけ計算して `scene.json` に書き、両方の描画系はそれを使うだけにしています。
元のテクスチャを持つ面は PLATEAU が配る Draco 圧縮のまま残るので、three.js 側には DRACOLoader が要ります。

## 未決

- プロジェクトから完成品をどう指すか (symlink、コピー、範囲と版だけを書いた参照)。
- 焼き込んでいない古い PLATEAU++ を読むための、レンダラーの描画時の補正をいつ外すか。
- Draco の圧縮をほどいたぶん GLB が約 3 倍になる。圧縮し直すか。

## 出典

- 建物モデル: 国土交通省 PLATEAU (東京都 2025 年度、テクスチャ付き LOD2 の 3D Tiles)
- 建物外形・空中写真・標高: 国土地理院の地理院タイルを加工
- 建物の属性: © OpenStreetMap contributors (ODbL)
