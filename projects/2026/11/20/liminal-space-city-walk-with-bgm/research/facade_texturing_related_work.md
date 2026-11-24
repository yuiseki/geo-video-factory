# 既存の形状に沿って外壁のテクスチャを復元する: 既存研究と既存実装の台帳

2026-11-23 に読んだ記録です。採否と理由、読んだ版 (コミット) を残します。検討し直す前に、まずここを見ます。

## 解く問題

建物の位置と立体形状は OpenStreetMap と PLATEAU にすでにある。いろいろな角度から撮った写真から外壁を切り出し、その形状のテクスチャとして復元する。写真だけから形を作る SfM や 3DGS とは別の課題で、形状は答えではなくガイドとして使う。

| 用語 | 意味 |
|---|---|
| Geometry-guided Facade Texturing | 既存の形状を使った外壁テクスチャの生成 |
| Model-based Texture Mapping | 既存の 3D モデルへの画像の投影 |
| Multi-view Texture Fusion | 複数視点の画像の統合 |
| Image-to-Model Registration | 写真と既存の 3D モデルの位置合わせ |
| Facade Orthorectification | 外壁画像の正射変換 |

## 台帳

ライセンスは、リポジトリの LICENSE と README、論文のページで確かめたものです。「コードを読む」は実装を参考にしてよいか、「使う」は依存として組み込んでよいかの判断です。

| 名前 | ライセンス | 読んだ版 | すること | 判断 |
|---|---|---|---|---|
| [louis-e/orthofacade](https://github.com/louis-e/orthofacade) | Apache-2.0 | a24e4ca349 (2026-09-02) | Mapillary のパノラマ、OSM の外形、Mapillary の SfM 点群から、壁ごとの正射テクスチャ。CPU だけ、機械学習なし | 考え方を採用。この課題に一番近い |
| [Project-PLATEAU/PLATEAU-SNAP-Server](https://github.com/Project-PLATEAU/PLATEAU-SNAP-Server) | Apache-2.0 | d194f8891e (2026-03-19) | スマートフォンの写真を PLATEAU の建物の面のテクスチャにするサービスのサーバー。撮れる面の一覧、正射変換、屋根面の抽出、CityGML の書き出し。画像処理は Python (OpenCV、shapely)、ほかは C# と PostGIS | 正射変換と面の選び方を読む候補。サーバー一式は使わない |
| [nmoehrle/mvs-texturing](https://github.com/nmoehrle/mvs-texturing) | BSD-3-Clause (LICENSE.txt。GitHub の表示は判定不能) | f3374298ac (2026-03-11) | 三角形メッシュと位置合わせ済みの写真から、面ごとに写真を選び、継ぎ目の色を合わせてアトラスにする (C++) | 統合の候補。README の節が「License, Patents and Citing」なので、使う前に特許の記述を読む |
| [misa-rtx/PhotoMesh](https://github.com/misa-rtx/PhotoMesh) | MIT | 00c2d70b90 (2026-06-08) | 写真測量の一式。`map_texture()` は COLMAP のデータから任意の .ply メッシュにテクスチャを貼る | 統合の候補。依存 (PyMeshLab など) のライセンスは未確認 |
| [seshing/OpenFACADES](https://github.com/seshing/OpenFACADES) | MIT | d382d821f5 (2026-10-29) | 街路のパノラマと OSM の外形から、建物が見える写真を選び (可視範囲の解析、物体検出)、透視投影の画像に切り出し、属性と説明文を付ける | 写真の選び方の参考。テクスチャは作らない |
| [WenzhaoTang/Texture2LoD3](https://github.com/WenzhaoTang/Texture2LoD3) ([arXiv 2504.05249](https://arxiv.org/abs/2504.05249)) | 記載なし | bcac62178e (2025-06-03) | 低い LoD の建物モデルの面を正射変換の的にしてパノラマを貼り、その正射画像の上で窓などを分割する | 論文の考え方だけ。ライセンスがないのでコードは読まない |
| [Ligo04/TwinTex](https://github.com/Ligo04/TwinTex) ([紹介ページ](https://vcc.tech/research/2023/TwinTex)) | All rights reserved (README) | 1e1d05a8ae | 面ごとに写真を選び、つなぎ、足りない所を塗る。配布は Windows の Houdini 用バイナリだけ | 見送り。再配布も改変もできない |
| DiffTex ([arXiv 2509.23336](https://arxiv.org/abs/2509.23336)) | arXiv の注記に「Patent Protected」 | 概要だけ | テクセルごとの混ぜる重みを、微分可能な描画で最適化する | 見送り。概要より先は読まない |
| Ogawa ほか 2024 ([Remote Sens. 16(11) 1858](https://www.mdpi.com/2072-4292/16/11/1858)) | 論文は CC BY 4.0 | 書誌と概要 (Crossref) | 全方位の街路画像と建物データを自動で対応づけ、3D 建物モデルを作る一貫の枠組み。神戸で検証 | 論文の考え方を参考。本文は未読 (出版社のページは自動取得を拒む) |

## orthofacade から持ち帰る考え方

- 出力から回す。壁の点を決め、その点が写真のどこに写るかを計算して画素を読む。射影変換も消失点の検出もいらない。
- OSM の外形は 0.5〜2 m ずれている。壁の面と軒の高さは、壁の近くの SfM の点で合わせ直す。
- 重ね合わせは、よく見えている数枚の中央値。通行人や車が落ちる。
- 隠れは 3 種類に分けて扱う: 植え込み (色)、手前の物 (SfM の奥行き)、ほかの建物 (外形への光線)。
- 建物ごとに検品用の一覧を出す。
- 公開している数字: 位置合わせを採用できた写真は 34%、複数の視点が 0.75 m 以内で一致した壁は 40%、テクスチャが付いた壁は 1030 面中 90 面。入力が街路のパノラマだけだと、壁の 1 割弱にしか届かない。

## この課題での使い分け (案)

| 段 | ここまでの実装 | 次に参考にするもの |
|---|---|---|
| 写真と形状の位置合わせ | `sfm_experiment/place_on_footprints.py`、`place_on_plateau.py` (1 か所で撮った写真の組) | 1 枚ずつの位置合わせ。PLATEAU の面の上で写真どうしが一致するように姿勢を直す |
| 写真の選択 | 全部使う | OpenFACADES の可視範囲、PLATEAU SNAP の「撮れる面」 |
| 正射変換 | `packages/pipeline/buildings/facade_ortho.py` | PLATEAU SNAP の面ごとの処理 |
| 統合 | 中央値、最良の 1 枚 | orthofacade の隠れの扱い、mvs-texturing の継ぎ目の色合わせ |
| 写っていない所 | なし | 生成 (ComfyUI)。形を保つ条件づけは別の試験 |
