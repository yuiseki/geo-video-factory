# packages のテスト方針

`packages/` の変更は、失敗するテストを先に追加してから実装する。

## TypeScript レンダラー

```bash
cd packages/renderer
npm test
npm run test:coverage
```

動画E2Eは `packages/renderer/test/fixtures/` にある対象名だけ再生成できます。renderer ディレクトリで次のように実行します。

```bash
VIDEO_TARGET=terrain-mt-omuroyama npm run test:video
```

`VIDEO_TARGET` は `base`、`earth-tokyo-station`、`terrain-mt-fuji`、`terrain-mt-omuroyama`、各 `choropleth-3d-*` を指定できます。未指定で `npm test` を実行すると、E2E対象動画を生成します。E2Eは `dist/test/video/` 全体を削除せず、対象ケースの動画と `.work/` 内だけを更新するため、手動生成した動画を保持します。

`test:coverage` は、行 65%、分岐 80%、関数 90% を下回ると失敗する。ブラウザーを起動する CLI 本体を含むため、行カバレッジは段階的に引き上げる。

- `src/lib.ts` の時間・座標・表示計算は、入力境界と決定性を単体テストする。
- `src/voice.ts` は、VOICEVOX を呼ばない draft モード、WAV、字幕、クレジット、立ち絵検査を単体テストする。
- `src/render.ts` は、引数、パス解決、フレーム時刻を純粋関数としてテストする。
- ブラウザー、VOICEVOX、FFmpeg を使う結合テストは、単体テストから分離する。

## Python パイプライン

```bash
python3 -m unittest discover -s packages/pipeline/tests -v
```

Python のカバレッジを含む全テストは、リポジトリのルートで次を実行する。

```bash
python3 -m pip install -r packages/pipeline/requirements-dev.txt
packages/test.sh
```

Python 実装の行カバレッジは 70% を下回ると失敗する。`packages/test.sh` は TypeScript の型検査も実行する。GitHub Actions は push と pull request で同じスクリプトを実行する。

- FFmpeg、ffprobe、Node.js の呼び出しは mock に置き換え、コマンドと結果検査をテストする。
- EXIF と PSD は小さな fake オブジェクトで分岐をテストする。
- カメラ効果とタイムラインは純粋関数として入力を変更しないこと、境界値、異常値をテストする。

不具合を直すときは、その不具合を再現するテストを追加して失敗を確認する。テストが通る最小の修正を入れた後、重複だけを整理する。
