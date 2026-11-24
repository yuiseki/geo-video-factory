# 伊豆の温泉と昭和のゴールドラッシュ

企画・地理調査から、ずんだもんと四国めたんの掛け合いによる9章の解説動画を作るプロジェクトです。

- `script.md`：台本
- `storyboard.md`：地図と図解の初期コンテ
- `research/`：調査とデータの取得・分析記録
- `flyover/scripts/build_episode.py`：台本とコンテから各章のショットと章マニフェストを生成
- `flyover/chapters-v0.2.0.json`：章の並び
- `flyover/shots/episode-v0.2.0/`：本編の各章のショット定義

OSMの施設388件は、記録された候補から選んだ標本です。施設全体の公式な数ではありません。鉱山9地点と最寄り施設との距離は概略の地点を含む地図上の直線距離です。46.1 kmは河川網を接続して推定した距離で、汚染の到達範囲を示すものではありません。図の線は模式的な位置関係を表します。

## 書き出し

Node.js、Playwright、ffmpeg、Python、Pillow、日本語フォント、VOICEVOXエンジンを用意します。立ち絵は坂本アヒル氏のPSDを `packages/pipeline/narration/psd_sprites.py` で `flyover/assets/chara/{zundamon,metan}/` に書き出します。PSD自体と生成画像はリポジトリに含めません。資源制限はホストの規則に従ってください。

```sh
cd packages/renderer && npm run build && cd ../..
python3 projects/2026/11/19/izu-hot-spring-and-gold/flyover/scripts/build_episode.py
python3 packages/pipeline/video/chapter_pipeline.py \
  projects/2026/11/19/izu-hot-spring-and-gold/flyover/chapters-v0.2.0.json \
  --out projects/2026/11/19/izu-hot-spring-and-gold/flyover/out/episode-v0.2.0 \
  --workers 2
```

出力は `flyover/out/episode-v0.2.0/episode.mp4` です。各章には3秒の無音のタイトルカードを挟みます。音声の尺に合わせて映像の長さを決めます。鉱山の円は代表地点から半径500 mの範囲を示し、実際の鉱区や施設の境界を示すものではありません。地名と専門用語はVOICEVOXの読みを確認し、必要な箇所に読み仮名を指定しています。

## 出典

- 国土地理院：地理院タイル（全国最新写真シームレス、標高）
- OpenStreetMap contributors：温泉関連施設・河川網（ODbL）
- 環境省「[富士箱根伊豆国立公園の特徴](https://www.env.go.jp/nature/nationalparks/list/fuji-hakone-izu/feature/)」：伊豆半島の地史
- 国立国会図書館「[産金法](https://hourei.ndl.go.jp/simple/detail?current=-1&lawId=0000026656)」および[国会会議録](https://kokkai.ndl.go.jp/simple/detail?current=-1&minId=100515254X00919490405)：昭和期の産金政策
- その他の地質・鉱山・災害に関する資料と分析上の制約は `research/` を参照。
- 音声：VOICEVOX:ずんだもん、VOICEVOX:四国めたん。立ち絵：坂本アヒル。

`credits.json` には調査時に挙げた写真候補も記録されています。本版は写真を取得できなかったため、地図とデータによって説明しています。
