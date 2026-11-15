---
name: geo-video-narration
description: 地理解説動画のVOICEVOX音声、複数話者の掛け合い、字幕タイミング、読み、立ち絵リアクション、BGMとの音量を設計する。台本を音声付き動画へ組み込むときに使う。
---

# 地理動画のナレーション

話者ごとの役割と口調を決め、1セリフで一つの情報を伝える。話題転換は次の章を予告する会話でつなぎ、章タイトルだけに接続を任せない。固有名詞や読み違いが起きる語には `speech` を指定する。

- VOICEVOX、文字数、間、字幕色、キャッシュ： [references/narration.md](references/narration.md)
- 立ち絵、表情、口パク、まばたき： [references/reaction.md](references/reaction.md)
- BGM、SE、ダッキング、サウンドブリッジ： [references/sound.md](references/sound.md)

音声の実尺がショット長を決める。下書きの文字数推定だけで本番タイミングを確定しない。完成前に音声付き動画を再生し、読み、話速、無音、字幕との同期、章間のつながりを確認する。VOICEVOXと素材のクレジットを映像と配布文へ残す。
