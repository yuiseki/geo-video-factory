---
name: geo-video-camera
description: 地図・地形・3D都市動画のカメラを、主題、位置関係、データ範囲、可読性に合わせて設計し検品する。ドリー、トラッキング、オービット、リビール、俯瞰などの選択や、急な移動、建物欠落、ラベル衝突の修正に使う。
---

# 地理動画のカメラ設計

各シーンで視聴者が理解する対象と位置関係を一文で決め、静止を含む候補から最小限の動きを選ぶ。MapLibreの `center`、`zoom`、`pitch`、`bearing` は実機の位置、画角、姿勢を独立制御するものではないため、映像上の近似として扱う。

- ショットレシピカード集（イージング規約・2.5D/3D 焦点固定・発話/BGM ビート同期・定番10型）： [references/shot-recipes.md](references/shot-recipes.md)
- 空撮技法の選択と組み合わせ： [references/drone-camera.md](references/drone-camera.md)
- 一般的なカメラ用語： [references/camera.md](references/camera.md)
- 速度、章境界、ラベル、写真線、3D範囲の検品： [references/camera-and-label-review.md](references/camera-and-label-review.md)

3D建物や点群を使う場合は、始点から終点まで実データの範囲内に置く。引いた結果、建物が消える、簡易形状だけになる、同じ単色建物が連続する場合は、その構図を採用しない。推定材質は地物ID単位で変化させ、固定シードでちらつきを防ぐ。

静止画一覧だけで完了とせず、通常速度の動画で最大加速、方向転換、ラベル接近、データ境界、写真マーカーの追従を確認する。
