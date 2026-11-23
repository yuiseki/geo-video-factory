# エージェント向け決定論モーション・アンチパターン集

HTML / CSS / JS / SVG でシーク可能な「動く図」を実装する際、通常の Web フロントエンド開発の習慣を持ち込むと、ヘッドレス Playwright での 1 フレーム書き出し時に**ズレ・透明化・再現不能**が発生する。頻発する 8 つのアンチパターンと修正例をまとめる。

実装の基本規約は [deterministic-engine.md](deterministic-engine.md) を参照する。

---

## 1. CSS `transition` / `@keyframes` / `animate-*` の混入

- **何が壊れるか**: CSS アニメーションはブラウザの実時間時計で非同期に進行する。フレームごとのスクリーンショット間隔は実時間と一致しないため、要素が途中で消えたり、高速・低速に乱れたり、`data-mode` 切替時に古い色が残る。
- **NG**:
  ```css
  .badge { transition: opacity 0.4s ease-out, transform 0.4s ease-out; }
  .pulse { animation: pulse 1.2s infinite; }
  ```
- **OK**: CSS の `transition` / `animation` を書かず（必要なら `transition: none !important`）、フレーム時刻 `t` からインラインスタイルを直接計算する。
  ```ts
  const u = easeOutCubic(progress(t, 0.5, 0.9));
  badge.style.opacity = String(u);
  badge.style.transform = `translate3d(0, ${(1 - u) * 16}px, 0)`;
  ```

---

## 2. 補間（`interpolate`）の範囲外クランプ忘れ

- **何が壊れるか**: `t < t0` や `t > t1` で補間値をクランプしないと、`opacity` が負や 1 超になり、`scale` や座標が画面外へ発散してレイアウトを破壊する。
- **NG**:
  ```ts
  const u = (t - 1.0) / (2.0 - 1.0); // t=0 で -1, t=4 で 3 になる
  el.style.transform = `scale(${u})`;
  ```
- **OK**: 必ず `[0, 1]` にクランプした進行度 `progress(t, t0, t1)` を通す。
  ```ts
  const u = easeOutCubic(progress(t, 1.0, 2.0)); // 常に 0..1
  el.style.transform = `scale(${0.85 + 0.15 * u})`;
  ```

---

## 3. 前フレーム状態への累積更新（ステートフル描画）

- **何が壊れるか**: `x += vx` やリアクティブな状態更新（`useState` / `useEffect` 等）で位置を積み上げると、任意時刻へのシーク（再描画や静止画抽出）や `--fps` の変更で軌道が変わる。
- **NG**:
  ```ts
  let x = 0;
  function renderFrame() {
    x += 4; // 30fps と 60fps で到達位置が 2 倍変わる
    plate.setAttribute('transform', `translate(${x}, 0)`);
  }
  ```
- **OK**: 時刻 `t` からの閉じた式（純粋関数）で毎回絶対値を計算する。
  ```ts
  function renderAt(t: number) {
    const x = interpolate(t, [0.5, 2.5], [0, 240], easeInOutCubic);
    plate.setAttribute('transform', `translate(${x}, 0)`);
  }
  ```

---

## 4. FPS のハードコード

- **何が壊れるか**: `frame === 30` や `frame / 30` を直書きすると、下書きの `--fps 15` や本番の `--fps 60` に切り替えた途端にすべてのタイミングが狂う。
- **NG**:
  ```ts
  const opacity = clamp01((frame - 30) / 15); // 30fps 前提
  ```
- **OK**: 常に**秒（`t`）**で区間を定義し、呼び出し側で `t = frame / fps` を渡す。
  ```ts
  const opacity = progress(t, 1.0, 1.5); // どの fps でも 1.0s〜1.5s
  ```

---

## 5. CSS 初期 `transform` と JS アニメーションの競合

- **何が壊れるか**: CSS で中央揃え用に `transform: translate(-50%, -50%)` を指定した要素に対し、JS やタイムラインライブラリが `el.style.transform = 'scale(...)'` を上書きすると、中央揃えが吹き飛んで位置がズレる。
- **NG**:
  ```css
  .callout { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); }
  ```
  ```ts
  callout.style.transform = `translateY(${dy}px)`; // translate(-50%, -50%) が消える
  ```
- **OK**: **配置用の親ラッパー**と**アニメーション用の子要素**を分けるか、全成分を JS 側で 1 本の `transform` に合成する。
  ```html
  <div class="callout-anchor"><!-- left/top + translate(-50%, -50%) -->
    <div class="callout-motion"><!-- JS はここだけに transform を適用 --></div>
  </div>
  ```

---

## 6. メディア要素・外部ランタイムの自動再生放置

- **何が壊れるか**: `<video autoplay>` や `video.play()`、`autoplay: true` の Lottie、開始済みの GSAP タイムラインは、キャプチャ待機中にも勝手に先へ進み、フレームと音・図が同期しなくなる。
- **NG**:
  ```ts
  const tl = gsap.timeline(); // デフォルトで即座に再生開始してしまう
  ```
- **OK**: 必ず停止状態で初期化し、`renderAt(t)` から明示的に時刻をシークする。
  ```ts
  const tl = gsap.timeline({ paused: true });
  // renderAt(t) 内で tl.time(t, false);
  ```

---

## 7. 非決定論的乱数・現在時刻の使用

- **何が壊れるか**: 粒子・波紋・揺らぎの配置に `Math.random()` を使うと、再レンダリングごとに配置が変わり、連番フレーム間でノイズのように激しく点滅する。
- **NG**:
  ```ts
  const jitter = (Math.random() - 0.5) * 4;
  ```
- **OK**: 要素インデックス `i` や固定シードから決定論的ハッシュで算出する。
  ```ts
  const hash01 = (n: number): number => {
    const x = Math.sin(n * 12.9898 + 78.233) * 43758.5453;
    return x - Math.floor(x);
  };
  const offset = (hash01(i) - 0.5) * 4;
  ```

---

## 8. 入れ子タイミングの二重オフセットと直列尺の手計算ズレ

- **何が壊れるか**: 親コンテナと子要素の両方に開始時刻のオフセットを掛けると表示タイミングが二重にズレる。また、各フェーズの開始秒をリテラルで手書きすると、途中の尺を変えた際に後続フェーズが重なる。
- **NG**:
  ```ts
  // 親と子の両方で開始時刻を引き算してしまい、子が表示されない
  const parentT = t - 1.0;
  const childU = progress(parentT, 1.0, 1.5); // 実際は t=2.0..2.5 にズレる
  ```
- **OK**: すべての区間を「グローバル時刻 `t`（秒）」でフラットに定義し、前フェーズの終了時刻から相対計算する。

---

## 決定論シーク検証チェック（書き出し前）

カスタム図版を本番レンダリングへ組み込む前に、次の 2 点を確認する。

1. **順逆シーク一致テスト**: 代表時刻 `t`（例：総尺の中間 `t = 2.0s`）について、`renderAt(0) → ... → renderAt(2.0)` で得たフレームと、`renderAt(4.0) → renderAt(2.0)` で逆シークして得たフレームを目視またはピクセル差分で比較し、完全に一致することを確認する。
2. **FPS 変更テスト**: 同じ時刻 `t` を `--fps 10`（下書き）と `--fps 30`（本番）で書き出したとき、同じ秒数の位置で要素の座標・長さ・数値が一致することを確認する。
