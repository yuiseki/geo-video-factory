---
name: geo-video-production
description: 地理・歴史解説動画を企画し、章別制作、素材管理、並列レンダリング、結合、検品、版番号付き公開まで統括する。複数章や複数素材を含む動画全体を制作するときに使う。単一ショットのJSONやカメラ調整だけなら専用スキルを使う。
---

# 地理動画の制作統括

動画全体の目的、視聴者、主張、章構成、必要素材、出典、完成条件を先に整理する。実装と素材の責務は次のスキルへ渡す。

- 地図描画、ショットJSON、書き出し環境：`geo-video-renderer`
- PLATEAU、OSM補完、建物材質、3D被覆：`geo-video-3d-buildings`
- カメラ技法、速度、地名、データ範囲の検品：`geo-video-camera`
- VOICEVOX、掛け合い、字幕、立ち絵：`geo-video-narration`
- 写真、図解、画面効果、見た目の文法：`geo-video-visuals`
- 素材収集（いらすとや、Wikimedia Commons 等）、ライセンス・重複・EXIF・画像 ID 管理：`geo-video-materials`
- 利用者が良いと感じた参考動画の分析：`geo-video-reference-analysis`。章立ての前に、伸びた動画の入り口、骨組み、終わり方の傾向 (その `references/findings.md`) を読む

複数章では章ごとに独立したショットJSONと出力先を持たせ、章間に無音のタイトルカードなど明確な編集点を置く。独立章は資源上限を共有し、最大3並列を目安にする。版は git のコミットとタグで管理し、書き出しは同じ出力先に描き直す (`AGENTS.md` の「進め方の原則」)。

企画から最終書き出しまでのロール別チェックリスト（監督/脚本・撮影・美術・特効・音響）、工程ごとの品質ゲート（Pass/Fail条件）、動画タイプ別の推奨パイプラインは [references/preproduction-gates.md](references/preproduction-gates.md) を読む。

素材収集、写真のEXIFと撮影地点、章パイプライン、結合、公開、ハッシュとHTTP応答の確認が必要な場合は [references/production-workflow.md](references/production-workflow.md) を読む。

地名の座標、川や路線の形、経路を調べるときは [references/osm-services.md](references/osm-services.md) (Nominatim、Overpass、Valhalla、ベクトルタイル)。報道や資料から台本を書くときは [references/script-from-sources.md](references/script-from-sources.md)、概要欄、チャプター、タグ、縦長版を作るときは [references/publishing.md](references/publishing.md) を読む。

完成報告前に、音声付きの通し動画、章境界、出典、画像の重複、カメラ速度、ラベル、公開ファイルの一致を確認する。
