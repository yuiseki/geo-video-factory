# PLATEAU 3D Tiles の固定レンダリング

## 構成

動画用途では、公開 3D Tiles を実行時に逐次選択せず、準備段階で必要な leaf tile を固定する。

1. PLATEAU の公開カタログから年度、LOD、テクスチャ有無を確認する。
2. root tileset から子 tileset を再帰的にたどる。
3. scene bbox と `boundingVolume.region` が交差する leaf だけを選ぶ。region の単位はラジアンである。
4. b3dm または glTF を取得し、動画用ディレクトリへ保存する。
5. manifest に source URL、ローカルGLB、RTC中心、建物ID、region、depth、bytes、利用拡張を記録する。
6. manifest の全GLBをロードし終えてから撮影を開始する。

固定ロードには、実行時 LOD のポップインを防ぎ、再レンダリング結果を揃えやすい利点がある。代わりにメモリ消費が増えるため、カメラが実際に通る範囲から bbox を決める。

## 建物ID

- b3dm では batch table の `gml_id` を調べる。
- native glTF では `EXT_structural_metadata` の property table を調べる。
- leaf tile 間で建物IDの重複数を集計する。
- 補完建物との照合に使えるよう、IDの由来も manifest に残す。

## RTC と座標変換

`CESIUM_RTC` の中心値は軽量化前に manifest へ分離保存する。最適化後のGLBから拡張を外す場合も、中心値を失わない。

ECEF をローカル ENU に変換する基本手順は次のとおり。

1. シーン原点の緯度・経度・楕円体高を ECEF に変換する。
2. vertex の ECEF と原点 ECEF の差を求める。
3. 差ベクトルを East、North、Up の各基底へ射影する。
4. glTF の Y-up をローカル Z-up に合わせる。
5. MapLibre の Mercator 座標と meter scale に変換する。

WGS84 の定数は `a = 6378137`、`e² = 6.69437999014e-3` を使う。試作で経験的な鉛直オフセットを使った場合は、測地的に正しい標高補正と混同せず manifest または制作記録へ明記する。

tile の transform は RTC 以外も含みうる。対応していない行列を検出したら、その tile を誤配置するより準備処理を失敗させる。

## MapLibre と Three.js

- MapLibre custom layer 内で MapLibre と同じ WebGL context を使う。
- `GLTFLoader` と、必要なら `DRACOLoader` で固定GLBを読む。
- 色空間は sRGB、tone mapping は ACES 系から調整を始める。
- 同時デコード数を制限する。既存試作では3並列が安定した。
- ロード済みtile数、triangle数、draw call数、material数をログへ出す。
- `cesium.com` と `cesium.io` へのリクエストがないことをネットワークログで確認する。

## 容量設計

広域例では数百tile、数万建物ID、数百MBのGLBになりうる。準備処理と実データ検査はリポジトリの資源制限規則に従って実行する。カメラ外のtileを増やして画面を埋めるより、必要被覆を先に計算する。
