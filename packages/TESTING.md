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

`VIDEO_TARGET` は `base`、`earth-tokyo-station`、`terrain-mt-fuji`、`terrain-mt-fuji-seasonal`、`terrain-mt-omuroyama`、各 `choropleth-3d-*`、`buildings-asakusa`、`buildings-asakusa-sumida-river` を指定できます。PLATEAU の建物 E2E は `buildings-` prefix を使います。例: `VIDEO_TARGET=buildings-asakusa npm run test:video`。最終出力はそれぞれ `dist/test/video/<testname>.mp4` です。PLATEAU の実データは fixture に含めず、欠落時に `.work/<testname>/project/` へ取得・生成してキャッシュします。未指定で `npm test` を実行すると、E2E対象動画を生成します。E2Eは `dist/test/video/` 全体を削除せず、対象ケースの動画と `.work/` 内だけを更新するため、手動生成した動画を保持します。

素材を準備する E2E (`buildings-*` など) は、Python から `packages/pipeline` を呼びます。既定の `python3` に `packages/pipeline/requirements-dev.txt` の依存 (DracoPy、shapely など) が無い場合は、依存を入れたインタープリターを `GVF_PYTHON` に指定します。例: `GVF_PYTHON=$PWD/../pipeline/.venv/bin/python VIDEO_TARGET=buildings-asakusa-sumida-river npm run test:video`。

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

`terrain-mt-fuji-seasonal` は Sentinel-2 と地理院オルソから四季画像を初回取得・生成し、`.work/terrain-mt-fuji-seasonal/project/fuji-seasons/` にキャッシュします。Python の `numpy`、`Pillow`、`pyproj`、`scipy` とネットワーク接続が必要です。冬の雪は Sentinel-2 の SCL 積雪分類を使用します。

## 性能の回帰を防ぐテスト

壁時計の閾値は CI の揺れに耐えるよう余裕を大きく取り、構造の予算 (数えられるもの) を主にする。

- `test/map-style.test.ts`: 既定のスタイルのレイヤー数・ソース数、オーバーレイ 1 つあたりの追加数、500 ショットの組み立て時間。
- `test/texture-tone.test.ts`: 2048x2048 のテクスチャの解析時間。
- `test/bundle-budget.test.ts`: `dist/src/page/flyover.js` の大きさ (現状 約 2.8MB、上限 3.4MB)。上げるときは理由をコミットに書く。

`src/page/tile-math.ts` はタイルプロトコル (`imgtile`、`gsiclear`) の純粋な計算で、ブラウザ API を使わず Node で単体テストする。`src/render.ts` の ffmpeg の引数 (`mp4EncodeArgs`、`stillsSheetArgs`、`loudnormSecondPass`) も同じ方針で、`main()` から切り出してテストする。
