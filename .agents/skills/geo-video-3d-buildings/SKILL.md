---
name: geo-video-3d-buildings
description: PLATEAU、OpenStreetMap、地理院オルソを組み合わせ、Cesium ion に依存せず都市の3D建物映像を作る。PLATEAU 3D Tiles の取得と固定化、ECEF座標変換、欠損建物の補完、建物ごとの色・推定テクスチャ、カメラ範囲とデータ被覆の整合、品質検証が必要なときに使う。
---

# Geo Video 3D Buildings

PLATEAU を主役に、欠損を OSM と地理院オルソで補い、動画レンダリングに耐える都市モデルを作る。

## 責務

- PLATEAU の公開 3D Tiles を調査し、対象範囲の leaf tile を事前に固定する。
- CesiumJS / Cesium ion を使わず、Three.js と MapLibre の同一 WebGL コンテキストで描画する。
- PLATEAU がない建物だけを OSM または CityGML 由来の押し出し形状で補う。
- 地理院オルソから色を推定し、建物単位の決定的な変化を加えて街並みに馴染ませる。
- カメラ全行程が実データの被覆内に収まることを確認する。
- データ出典、推定表現、位置・時点の制約を明示する。

動画全体の工程は `geo-video-production`、MapLibre のレンダリング基盤は `geo-video-renderer`、カメラ演出は `geo-video-camera` を使う。このスキルは3D建物データとその見た目、被覆整合を担当する。

## 作業手順

1. 対象地点、カメラ経路、必要な引きの範囲から bbox を決める。
2. PLATEAU の年度・LOD・テクスチャ有無を比較し、利用する tileset を記録する。
3. tileset tree をオフラインでたどり、bbox と交差する leaf tile をすべて選ぶ。
4. tile を取得し、glTF、建物ID、RTC中心、region、拡張情報を manifest に固定する。
5. 近景と遠景でテクスチャ解像度を変え、形状とUVを保ったまま軽量化する。
6. PLATEAU 建物IDと補完データを照合し、重複を除いて欠損だけを押し出す。
7. オルソ色を補完建物へ割り当て、彩度と明度を抑えて外壁向けに調和させる。
8. PLATEAU の低情報な灰色材質には、建物IDを種にした疑似外観を加える。
9. 全モデルのロード完了後に最初のフレームを描画する。
10. カメラ経路とデータ被覆を突き合わせ、静止画と実時間動画の両方で検証する。

## 判断規則

- 詳細な PLATEAU モデルがある建物では、それを優先する。
- OSM 補完は空間重複を除いた後に追加する。高さは `height`、次に `building:levels × 3m` を使い、推定元を保存する。
- 建物の屋根色を外壁へそのまま使わない。色を暗くし、垂直方向の勾配を加える。
- 同一材質を共有する建物にも建物単位の変化を与える。材質単位だけの乱数では連続する建物が同色になる。
- 乱数は建物IDから決定的に生成する。フレームごとに変えてちらつかせない。
- 元の写真テクスチャに色差がある面は弱く処理し、無彩色に近い面だけ疑似外観を強める。
- 推定した窓、設備、外壁模様を実在情報として扱わない。
- 3D建物がない領域までカメラを引かない。広域説明が必要なら編集点を置き、別の2D地図カットにする。
- 実行時の LOD 切替に依存しない。対象 leaf tile を固定し、ポップインを避ける。
- 未対応の tile transform は黙って無視せず、処理を止めて記録する。

## 参照資料

- 取得、座標変換、固定ロード: [architecture.md](references/architecture.md)
- PLATEAU 欠損と OSM・オルソ補完: [fallback-data.md](references/fallback-data.md)
- テクスチャ最適化と疑似外観: [materials.md](references/materials.md)
- カメラ被覆と受入検証: [validation.md](references/validation.md)

必要な資料だけを読む。実装前に architecture、灰色・白い建物を直す場合は materials、補完を作る場合は fallback-data、書き出し前は validation を参照する。
