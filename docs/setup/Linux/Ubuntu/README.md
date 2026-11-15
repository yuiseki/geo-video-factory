# Ubuntu (Linux) での開発環境セットアップ

Ubuntu 系 Linux における依存ソフトウェアのインストールと初期確認の手順です。全体の流れや共通の設定は [SETUP.md](../../../../SETUP.md) を参照してください。

## 1. OS の基本パッケージ

```bash
sudo apt update
sudo apt install -y git curl ffmpeg python3 python3-venv python3-pip \
  fontconfig fonts-noto-cjk
```

Node.js（保守中の LTS 版）、Docker、gitleaks、`uv` は、Ubuntu 標準パッケージが古い場合があるため、それぞれの公式手順でインストールしてください。

インストール後、`PATH` から各コマンドを実行できることと日本語フォントが入ったことを確認します。

```bash
git --version
node --version
npm --version
python3 --version
ffmpeg -version
ffprobe -version
gitleaks version
uv --version
fc-list :lang=ja | head
```

## 2. Playwright Chromium と不足ライブラリー

`packages/renderer` で Playwright の Chromium を導入します。

```bash
cd packages/renderer
npm install
npx playwright install chromium-headless-shell
npm run build
```

Linux で Chromium の共有ライブラリーが不足して起動できない場合は、Playwright のガイドに従ってシステム依存パッケージを追加してください。

```bash
npx playwright install-deps chromium-headless-shell
```

## 3. Python 仮想環境 (venv)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install Pillow
```

## 4. Docker での VOICEVOX エンジン起動

Linux では、VOICEVOX エンジンの Docker 版を利用できます。利用する CPU または GPU に対応した安定版イメージを選び、ポート `50021` をローカルホスト（`127.0.0.1`）だけに公開してください。イメージ名とタグは VOICEVOX エンジンの公式配布情報で確認します。

起動後の確認：

```bash
curl http://127.0.0.1:50021/version
curl http://127.0.0.1:50021/speakers
```

## 5. 最小動作確認（`/tmp` を使用）

```bash
mkdir -p /tmp/geo-video-smoke
cp -a .agents/skills/geo-video-renderer/assets/template/. /tmp/geo-video-smoke/
node packages/renderer/dist/src/render.js \
  /tmp/geo-video-smoke/shots/example.json \
  --project /tmp/geo-video-smoke \
  --out /tmp/geo-video-smoke/out/example \
  --stills 2 --no-voice
```

GPU を利用できない環境では `FLYOVER_GL=swiftshader` を付けて実行します（ソフトウェア描画のため大幅に遅くなります）。
