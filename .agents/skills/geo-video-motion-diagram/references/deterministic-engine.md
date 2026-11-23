# 決定論的アニメーション実装規約

`packages/renderer/` は Playwright で 1 フレームずつ時刻 `t` を進めてキャプチャする決定論的レンダラーである。動く図（カスタム HTML/SVG/Canvas/Three.js 図版、およびレンダラー拡張）を作る際は、フレームレートやマシン速度に依存しない完全な再現性と**任意時刻へのシーク可能性**を保つ。

AI エージェントがやりがちな決定論違反と修正例は [agent-motion-antipatterns.md](agent-motion-antipatterns.md) を参照する。

---

## 1. 禁止事項（非決定論的 API）

以下の実時間依存・乱数 API に視覚状態の変化を委ねない。書き出し速度や `--fps` の変更でズレや飛びが発生する。

- CSS `transition` / `@keyframes` / ユーティリティ `animate-*`（MapLibre のスタイル変更も `transition` を `0` にして使う）
- `setInterval` / `setTimeout`
- `requestAnimationFrame`
- `Date.now()` / `performance.now()`
- `Math.random()`（揺らぎが必要な場合は決定論的ハッシュまたは固定シード擬似乱数を使う）

---

## 2. シーク可能タイムラインとコンポーネント分割の規約

### 2.1 べき等・ステートレスな `renderAt(t)` 契約

カスタム図版ページは、外部（Playwright）から任意の時刻 `t`（秒）を受け取ってその瞬間の全 DOM/SVG/Canvas 状態を確定させる関数（例：`window.renderAt(t)`）を公開する。

- **シーク不変性**: `0 → t` へ順に再生したときと、`T → t` へ逆シークしたとき、あるいは `t` へ直接ジャンプしたときで、1 ピクセルの差異もなく同一フレームを描画できること。
- **FPS 非依存**: タイムラインの基準は常に**秒（`t`）**で記述する。フレーム番号 `30` や `60` をロジックにハードコードせず、必要な場合のみ `t = frame / fps` を通じて換算する。

### 2.2 フラットなフェーズ定義と相対連鎖

要素ごとに開始時刻を散らして手書きすると、前半の尺を 0.5 秒伸ばしただけで後半が衝突する。タイムラインは**フラットなフェーズ表**として先頭で一元管理し、親要素と子要素にタイミングを二重で入れ子にしない。

```ts
interface Phase {
  id: string;
  start: number;
  duration: number;
}

// 尺の配列から連続・オーバーラップした区間 [t0, t1] を決定論的に生成
const phases = (() => {
  const base = { start: 0.0, end: 0.5 };
  const move = { start: base.end, end: base.end + 1.6 };
  const impact = { start: move.end - 0.15, end: move.end + 0.75 };
  return { base, move, impact };
})();
```

### 2.3 コンポーネント分割（1 責務＝1 純粋描画関数）

図版が複雑になっても 1 つの巨大な更新関数に押し込めず、**「タイムライン計算（純粋関数）」と「部品ごとの DOM/SVG 反映」**を分離する。

- `computeState(t)`: 時刻 `t` から各要素の数値（座標・長さ・透明度・ラベル状態）を返す純粋関数。DOM に触らないため単体テストしやすい。
- `applyLayerX(el, state.layerX)`: 計算済みの値だけを DOM/SVG 属性へ反映する関数。

### 2.4 外部ランタイムのシーク制御

GSAP・`lottie-web`・Three.js 等の外部ランタイムをカスタム図版で使う場合は、**自動再生を必ず無効化**し、レンダラー側から時刻 `t` でシークする。

- **GSAP**: `gsap.timeline({ paused: true })` で構築し、フレームごとに `tl.time(t, false)` でヘッド位置を固定する。
- **Lottie (`lottie-web`)**: `autoplay: false` で読み込み、フレームごとに `anim.goToAndStop(Math.min(t * anim.frameRate, anim.totalFrames - 1), true)` を呼ぶ。
- **Three.js**: `requestAnimationFrame` ループを回さず、`renderAt(t)` 内でオブジェクト姿勢・カメラ・シェーダ uniform (`uTime = t`) を更新してから `renderer.render(scene, camera)` を 1 回だけ呼ぶ。

---

## 3. 時刻 `t` 駆動の補間と解析解スプリングの数値設計

### 3.1 クランプ付き補間（`interpolate`）

すべての視覚状態は、区間外の発散を防ぐために**両端クランプを既定**とする補間関数で計算する。

```ts
const clamp01 = (x: number): number => Math.max(0, Math.min(1, x));

const progress = (t: number, t0: number, t1: number): number =>
  t1 <= t0 ? (t >= t1 ? 1 : 0) : clamp01((t - t0) / (t1 - t0));

const easeOutCubic = (u: number): number => 1 - Math.pow(1 - u, 3);
const easeInOutCubic = (u: number): number =>
  u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;

const interpolate = (
  t: number,
  [t0, t1]: [number, number],
  [v0, v1]: [number, number],
  easing: (u: number) => number = (u) => u,
): number => {
  const u = easing(progress(t, t0, t1));
  return v0 + (v1 - v0) * u;
};
```

### 3.2 解析解スプリング（`springAt`）とプリセット設計

有機的な着地や構造展開にバネの物理感を使いたい場合も、前フレームの速度を積分するループ（Euler 法等）は使わず、**経過時間 `dt = t - t0` の閉じた解析解（減衰調和振動）**で評価する。これによりどの FPS・シーク順でも完全に同じ値が得られる。

```ts
interface SpringConfig {
  stiffness?: number; // ばね定数 k
  damping?: number;   // 減衰係数 c
  mass?: number;      // 質量 m
}

function springAt(dt: number, config: SpringConfig = {}): number {
  if (dt <= 0) return 0;
  const k = config.stiffness ?? 180;
  const c = config.damping ?? 28;
  const m = config.mass ?? 1;
  const w0 = Math.sqrt(k / m);
  const zeta = c / (2 * Math.sqrt(k * m));

  if (zeta < 1) {
    const wd = w0 * Math.sqrt(1 - zeta * zeta);
    return 1 - Math.exp(-zeta * w0 * dt) * (Math.cos(wd * dt) + ((zeta * w0) / wd) * Math.sin(wd * dt));
  }
  if (Math.abs(zeta - 1) < 1e-6) {
    return 1 - Math.exp(-w0 * dt) * (1 + w0 * dt);
  }
  const r = w0 * Math.sqrt(zeta * zeta - 1);
  const r1 = -zeta * w0 + r;
  const r2 = -zeta * w0 - r;
  return 1 - (r2 * Math.exp(r1 * dt) - r1 * Math.exp(r2 * dt)) / (r2 - r1);
}
```

| 用途プリセット | `stiffness` | `damping` | `mass` | 減衰比 $\zeta$ | 動きの性格と使いどころ |
|---|---|---|---|---|---|
| **スムーズ着地（バウンスなし）** | `180` | `28` | `1.0` | `1.04` | 解説図のラベル・パネル・断面層の標準。跳ねずに素早く落ち着く |
| **軽快な強調（微バウンス）** | `220` | `18` | `1.0` | `0.61` | 衝突点マーカー・到達ピンなど、1 箇所だけ視線を奪いたい場面に限定 |
| **重厚な構造展開** | `120` | `24` | `1.4` | `0.93` | プレート塊・大型インフラ構造の移動。質量感を持たせる |

---

## 4. HTML / SVG / DOM での代表的な実装パターン

| 表現 | 時刻 `t` での実装方法 |
|---|---|
| **線・矢印・境界の伸長（`draw`）** | SVG `<path>` の `getTotalLength()` を取得し、`stroke-dasharray = L`、`stroke-dashoffset = L * (1 - easeInOutCubic(u))` をフレームごとに設定する。 |
| **図形・ラベルの出現（`fade` / `rise`）** | `opacity = u`、`transform = translate3d(0, (1 - u) * 18px, 0)` のように `t` から直接設定する。 |
| **移動・衝突** | 始点 `(x0, y0)` と終点 `(x1, y1)` を `interpolate(t, [t0, t1], [x0, x1], easeInOutCubic)` で補間する。 |
| **数値カウントアップ（`counter`）** | `font-variant-numeric: tabular-nums;` を指定した要素に、`Math.round(interpolate(t, [t0, t1], [startVal, endVal], easeOutCubic))` を書き込む。 |
| **状態一括切替（`data-mode`）** | `t >= tAlert` の条件でルート要素に `data-mode="alert"` 等を設定し、CSS 変数で正常色から警戒色へ画面全体を一斉反転させる（`transition: none` を徹底）。 |

---

## 5. 動画圧縮（H.264）と視認性の規約

- **高周波パターン・フリッカーの抑制**: 走査線（`repeating-linear-gradient`）やグリッド背景を入れる場合は不透明度を **4〜6% 以下**に抑える。H.264 圧縮でブロックノイズや文字潰れを起こす常時フリッカー点滅・過剰なグロー（Bloom）・極小フォントは避ける。
- **色以外での判別性**: 強調や状態変化は塗り色だけでなく、太さ・形・ラベル文字の切り替わりを併用する。
- **Playwright 実行環境（macOS）**: Chromium の WebGL / Screenshot 安定性のため、独自スクリプトで連番書き出しする場合は `args: ["--use-gl=angle", "--use-angle=metal"]` の利用を検討する（`deviceScaleFactor` 指定時のプロトコルエラーに注意）。
