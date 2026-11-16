# サムネイルの設計基準と生成手順

## 1. 構図と文字の設計（`geo-video-art-direction` の適用）

- **文字数を絞る**: サムネイルは読ませる記事ではなく一瞬の看板。主見出しは **8〜14 文字前後** に絞り、補足（地名・年代・データ名）は小さなキッカー／ラベルへ逃がす。
- **右下を避ける**: YouTube 一覧では右下に動画の再生時間バッジが重なる。主見出しや重要な数値・地名ラベルは左側または上側へ寄せる。
- **実ウェイトと暗いグラデーション**: 地形や空中写真の上に白文字を置くときは、左〜下側に暗い半透明グラデーションを敷き、文字側には実ウェイトの太字（`Noto Sans CJK JP` Black/Bold）と明確な縁取り／ドロップシャドウを使う。
- **主図を見せる**: 地図や 3D 建物の「一番見せたい場所」を文字で覆い隠さない。背景フレームの切り出し時刻をずらすか、文字ブロックを反対側の余白へ寄せる。

## 2. 生成コマンド例

プロジェクト作業ディレクトリ（例: `projects/YYYY/MM/DD/<slug>/`）に `thumbnail.html` をコピーし、`out/thumbnail/` へ書き出す手順。

```bash
# 1. 本編動画の指定秒（例: 12.5 秒）から代表フレームを抽出
mkdir -p out/thumbnail
ffmpeg -y -ss 12.5 -i out/episode.mp4 -frames:v 1 out/thumbnail/hero.png

# 2. テンプレートをコピーして見出し・キッカーを編集
cp .agents/skills/geo-video-thumbnail/assets/thumbnail.html out/thumbnail/thumbnail.html
```

```bash
# 3. Playwright (Chromium) で 1280x720 撮影し、2MB 未満 JPG に変換
node -e '
const { chromium } = require("playwright");
const path = require("node:path");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.goto("file://" + path.resolve("out/thumbnail/thumbnail.html"), { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: "out/thumbnail/thumbnail.png" });
  await browser.close();
})();
'

ffmpeg -y -i out/thumbnail/thumbnail.png -q:v 3 out/thumbnail/thumbnail.jpg
ffprobe -v error -show_entries stream=width,height -of csv=p=0:s=x out/thumbnail/thumbnail.jpg
ls -lh out/thumbnail/thumbnail.jpg
```

## 3. 完了前の検品

- **縮小視認性**: 生成した `thumbnail.jpg` を横幅 200px 相当に縮小して表示し、文字が潰れず一瞬で内容が伝わるか確認する。
- **仕様確認**: `1280x720`・ファイルサイズ **2MB 未満** であることを確認する。
- **誤認防止**: イメージ写真や過去写真を使う場合は、サムネイルや概要欄で年代・出典の誤解を生まないようにする。
