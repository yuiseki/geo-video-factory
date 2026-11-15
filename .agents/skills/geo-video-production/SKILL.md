---
name: geo-video-production
description: 地理・歴史解説動画を企画し、章別制作、素材管理、並列レンダリング、結合、検品、版番号付き公開まで統括する。複数章や複数素材を含む動画全体を制作するときに使う。単一ショットのJSONやカメラ調整だけなら専用スキルを使う。
---

# 地理動画の制作統括

動画全体の目的、視聴者、主張、章構成、必要素材、出典、完成条件を先に整理する。実装と素材の責務は次のスキルへ渡す。

- 地図描画、ショットJSON、書き出し環境：`geo-video-renderer`
- カメラ技法、速度、地名、データ範囲の検品：`geo-video-camera`
- VOICEVOX、掛け合い、字幕、立ち絵：`geo-video-narration`
- 写真、図解、画面効果、見た目の文法：`geo-video-visuals`

複数章では章ごとに独立したショットJSONと出力先を持たせ、章間に無音のタイトルカードなど明確な編集点を置く。独立章は資源上限を共有し、最大3並列を目安にする。既存成果物を上書きせず、版番号付きで残す。

素材収集、写真のEXIFと撮影地点、章パイプライン、結合、公開、ハッシュとHTTP応答の確認が必要な場合は [references/production-workflow.md](references/production-workflow.md) を読む。

報道や資料から台本を書くときは [references/script-from-sources.md](references/script-from-sources.md)、概要欄、チャプター、タグ、縦長版を作るときは [references/publishing.md](references/publishing.md) を読む。

完成報告前に、音声付きの通し動画、章境界、出典、画像の重複、カメラ速度、ラベル、公開ファイルの一致を確認する。
