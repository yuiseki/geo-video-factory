# 決定論的アニメーション実装規約

`packages/renderer/` は Playwright で 1 フレームずつ時刻 `t` を進めてキャプチャする決定論的レンダラーである。動く図（カスタム HTML/SVG/Canvas/Three.js 図版、およびレンダラー拡張）を作る際は、フレームレートやマシン速度に依存しない完全な再現性を保つ。

## 1. 禁止事項（非決定論的 API）

以下の実時間依存・乱数 API に視覚状態の変化を委ねない。書き出し速度や `--fps` の変更でズレや飛びが発生する。

- CSS `transition` / `@keyframes`（MapLibre のスタイル変更も `transition` を `0` にして使う）
- `setInterval` / `setTimeout`
- `requestAnimationFrame`
- `Math.random()`（揺らぎが必要な場合は決定論的ハッシュまたは固定シード関数を使う）

## 2. 必須手法（時刻 `t` 駆動の純粋関数）

すべての視覚状態（位置・透明度・スケール・線長・数値・状態）を、フレーム時刻 `t`（秒）を入力とする純粋関数で計算する。

```ts
const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

// 区間 [t0, t1] における進行度 u (0..1)
const progress = (t: number, t0: number, t1: number) =>
  t1 <= t0 ? (t >= t1 ? 1 : 0) : clamp01((t - t0) / (t1 - t0));

// 減速イージング (out)
const easeOutCubic = (u: number) => 1 - Math.pow(1 - u, 3);

// 加減速イージング (inOut)
const easeInOutCubic = (u: number) =>
  u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
```

- **区間外クランプ**: 時刻 `t` が開始前（`t < t0`）なら `0`、終了後（`t > t1`）なら `1` に必ずクランプする。
- **解析解スプリング（Spring）**: 有機的な弾みが必要な場合も、リアルタイム物理演算ループではなく、経過時間 `dt = Math.max(0, t - t0)` に対して解析解（減衰調和振動）で評価できる関数として実装する。

## 3. HTML / SVG / DOM での代表的な実装パターン

| 表現 | 時刻 `t` での実装方法 |
|---|---|
| **線・矢印・境界の伸長（`draw`）** | SVG `<path>` の `getTotalLength()` を取得し、`stroke-dasharray = L`、`stroke-dashoffset = L * (1 - easeInOutCubic(u))` をフレームごとに設定する。 |
| **図形・ラベルの出現（`fade` / `rise`）** | `opacity = u`、`transform = translate3d(0, (1 - u) * 18px, 0)` のように `t` から直接設定する。 |
| **移動・衝突** | 始点 `(x0, y0)` と終点 `(x1, y1)` を `lerp(x0, x1, easeInOutCubic(u))` で補間する。 |
| **数値カウントアップ（`counter`）** | `font-variant-numeric: tabular-nums;` を指定した要素に、`Math.round(lerp(startVal, endVal, easeOutCubic(u)))` を書き込む。 |
| **状態一括切替（`data-mode`）** | `t >= tAlert` の条件でルート要素に `data-mode="alert"` 等を設定し、CSS 変数で正常色から警戒色へ画面全体を一斉反転させる。 |
| **Lottie 等の外部ベクターアニメ** | `lottie-web` を使う場合は `autoplay: false` とし、フレームごとに `anim.goToAndStop(frame, true)` を呼んで時刻同期させる。 |

## 4. 動画圧縮（H.264）と視認性の規約

- **高周波パターン・フリッカーの抑制**: 走査線（`repeating-linear-gradient`）やグリッド背景を入れる場合は不透明度を **4〜6% 以下**に抑える。H.264 圧縮でブロックノイズや文字潰れを起こす常時フリッカー点滅・過剰なグロー（Bloom）・極小フォントは避ける。
- **色以外での判別性**: 強調や状態変化は塗り色だけでなく、太さ・形・ラベル文字の切り替わりを併用する。
- **Playwright 実行環境（macOS）**: Chromium の WebGL / Screenshot 安定性のため、独自スクリプトで連番書き出しする場合は `args: ["--use-gl=angle", "--use-angle=metal"]` の利用を検討する（`deviceScaleFactor` 指定時のプロトコルエラーに注意）。
