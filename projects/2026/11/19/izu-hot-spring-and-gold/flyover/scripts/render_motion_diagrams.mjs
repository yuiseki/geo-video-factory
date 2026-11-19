import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require('../../../../../../../packages/renderer/node_modules/playwright');
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const WIDTH = 860;
const HEIGHT = 540;
const FPS = 30;
const DURATION = 4.0;
const TOTAL_FRAMES = Math.round(FPS * DURATION);

const outBase = path.resolve('out/motion_diagrams');
fs.mkdirSync(outBase, { recursive: true });

function buildHtmlPlateCollision() {
  return `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: ${WIDTH}px;
    height: ${HEIGHT}px;
    overflow: hidden;
    background: rgba(11, 15, 25, 0.94);
    font-family: "Noto Sans CJK JP", "Hiragino Sans", sans-serif;
    color: #f8fafc;
    border: 1.5px solid rgba(56, 189, 248, 0.35);
    border-radius: 14px;
    padding: 20px 24px 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .header {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .kicker {
    font-size: 16px;
    font-weight: 700;
    color: #38bdf8;
    letter-spacing: 0.04em;
  }
  .title {
    font-size: 26px;
    font-weight: 900;
    line-height: 1.25;
    border-left: 5px solid #f97316;
    padding-left: 12px;
  }
  .stage {
    position: relative;
    width: 100%;
    height: 390px;
  }
  svg {
    width: 100%;
    height: 100%;
    display: block;
  }
  .credit {
    font-size: 13px;
    color: #94a3b8;
    text-align: right;
  }
</style>
</head>
<body>
  <div class="header" id="header">
    <div class="kicker">第1章A：海底火山の北上と本州衝突</div>
    <div class="title">伊豆は元々「南洋の海底火山」だった</div>
  </div>
  <div class="stage">
    <svg viewBox="0 0 812 390">
      <defs>
        <linearGradient id="seaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#0ea5e9" stop-opacity="0.22" />
          <stop offset="100%" stop-color="#0369a1" stop-opacity="0.45" />
        </linearGradient>
        <linearGradient id="izuGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#fb923c" stop-opacity="0.9" />
          <stop offset="100%" stop-color="#c2410c" stop-opacity="0.6" />
        </linearGradient>
      </defs>

      <!-- Sea background & surface line -->
      <g id="sea">
        <rect x="0" y="135" width="812" height="225" rx="8" fill="url(#seaGrad)" />
        <line x1="0" y1="135" x2="812" y2="135" stroke="#38bdf8" stroke-width="2" stroke-dasharray="6 5" opacity="0.65" />
        <text x="798" y="126" text-anchor="end" fill="#7dd3fc" font-size="14" font-weight="700">海面</text>
      </g>

      <!-- Honshu (North American Plate side) -->
      <g id="honshu">
        <path d="M 16,355 L 16,95 L 165,95 L 222,145 L 245,355 Z" fill="#334155" stroke="#94a3b8" stroke-width="2.5" />
        <text x="115" y="195" text-anchor="middle" fill="#f8fafc" font-size="24" font-weight="900">本州</text>
        <text x="115" y="222" text-anchor="middle" fill="#cbd5e1" font-size="14" font-weight="700">（北アメリカプレート側）</text>
      </g>

      <!-- Submarine volcanoes on Philippine Sea Plate (background pair) -->
      <g id="submarines">
        <polygon points="565,355 620,175 675,355" fill="#0284c7" fill-opacity="0.28" stroke="#38bdf8" stroke-width="2.5" />
        <polygon points="680,355 735,190 790,355" fill="#0284c7" fill-opacity="0.28" stroke="#38bdf8" stroke-width="2.5" />
        <text x="678" y="340" text-anchor="middle" fill="#e0f2fe" font-size="16" font-weight="700">フィリピン海プレート上の海底火山群</text>
      </g>

      <!-- Moving Izu block (starts as submarine volcano on the right, moves left & uplifts above sea level) -->
      <g id="izu-block">
        <polygon id="izu-poly" points="-55,355 0,165 55,355" fill="#0284c7" fill-opacity="0.35" stroke="#38bdf8" stroke-width="3" />
        <polygon id="izu-poly-hot" points="-62,355 -28,95 28,95 62,355" fill="url(#izuGrad)" stroke="#f97316" stroke-width="3.5" opacity="0" />
      </g>

      <!-- Motion arrow (Northward collision) -->
      <g id="arrow-group">
        <path id="arrow-line" d="M 650,62 L 375,62" fill="none" stroke="#f97316" stroke-width="6" stroke-linecap="round" />
        <polygon id="arrow-head" points="355,62 385,48 385,76" fill="#f97316" opacity="0" />
        <text id="arrow-label" x="510" y="42" text-anchor="middle" fill="#fdba74" font-size="19" font-weight="900">南から北上・衝突（約100万年前〜）</text>
      </g>

      <!-- Collision impact ring (single non-looping pulse) -->
      <circle id="impact-ring" cx="255" cy="145" r="10" fill="none" stroke="#fb923c" stroke-width="4" opacity="0" />

      <!-- Result label for Izu Peninsula -->
      <g id="izu-result">
        <rect x="242" y="162" width="166" height="66" rx="8" fill="rgba(15, 23, 42, 0.88)" stroke="#f97316" stroke-width="2" />
        <text x="325" y="192" text-anchor="middle" fill="#fdba74" font-size="22" font-weight="900">伊豆半島</text>
        <text x="325" y="216" text-anchor="middle" fill="#f8fafc" font-size="14" font-weight="700">衝突して陸地化！</text>
      </g>
    </svg>
  </div>
  <div class="credit">模式図：伊豆半島ジオパーク資料をもとに作成</div>

  <script>
    const clamp01 = (x) => Math.max(0, Math.min(1, x));
    const progress = (t, t0, t1) => t1 <= t0 ? (t >= t1 ? 1 : 0) : clamp01((t - t0) / (t1 - t0));
    const easeOutCubic = (u) => 1 - Math.pow(1 - u, 3);
    const easeInOutCubic = (u) => u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
    const easeOutBack = (x) => {
      const c1 = 1.70158;
      const c3 = c1 + 1;
      return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
    };
    const lerp = (a, b, u) => a + (b - a) * u;

    const arrowLine = document.getElementById('arrow-line');
    const arrowLen = arrowLine.getTotalLength();
    arrowLine.style.strokeDasharray = String(arrowLen);

    window.__setTime = (t) => {
      // 0.00 - 0.35s: Stage & Honshu
      const uStage = easeOutCubic(progress(t, 0.0, 0.35));
      document.getElementById('header').style.opacity = String(uStage);
      document.getElementById('sea').setAttribute('opacity', String(uStage));
      const honshuEl = document.getElementById('honshu');
      honshuEl.setAttribute('opacity', String(uStage));
      honshuEl.setAttribute('transform', 'translate(' + lerp(-24, 0, uStage) + ', 0)');

      // 0.35 - 0.80s: Submarine volcanoes appear
      const uSub = easeOutCubic(progress(t, 0.35, 0.80));
      const subEl = document.getElementById('submarines');
      subEl.setAttribute('opacity', String(uSub));
      subEl.setAttribute('transform', 'translate(0, ' + lerp(18, 0, uSub) + ')');

      // 0.80 - 2.35s: Izu block moves from x=530 to x=325 and uplifts (morphs to orange above sea)
      const uIzuAppear = easeOutCubic(progress(t, 0.50, 0.85));
      const uMove = easeInOutCubic(progress(t, 0.85, 2.35));
      const uUplift = easeInOutCubic(progress(t, 1.55, 2.35));
      const izuX = lerp(530, 325, uMove);
      const izuEl = document.getElementById('izu-block');
      izuEl.setAttribute('opacity', String(uIzuAppear));
      izuEl.setAttribute('transform', 'translate(' + izuX + ', 0)');
      document.getElementById('izu-poly').setAttribute('opacity', String(1 - uUplift));
      document.getElementById('izu-poly-hot').setAttribute('opacity', String(uUplift));

      // 0.85 - 2.00s: Arrow draw
      const uArrow = easeInOutCubic(progress(t, 0.85, 1.90));
      const uArrowLabel = easeOutCubic(progress(t, 0.85, 1.25));
      document.getElementById('arrow-label').setAttribute('opacity', String(uArrowLabel));
      arrowLine.style.strokeDashoffset = String(arrowLen * (1 - uArrow));
      document.getElementById('arrow-head').setAttribute('opacity', uArrow > 0.88 ? String(clamp01((uArrow - 0.88) / 0.12)) : '0');

      // 2.25 - 2.75s: Single collision pulse
      const uPulse = progress(t, 2.25, 2.75);
      const ring = document.getElementById('impact-ring');
      if (uPulse > 0 && uPulse < 1) {
        ring.setAttribute('r', String(lerp(8, 72, easeOutCubic(uPulse))));
        ring.setAttribute('opacity', String((1 - uPulse) * 0.9));
      } else {
        ring.setAttribute('opacity', '0');
      }

      // 2.35 - 2.85s: Result label pops in
      const uRes = progress(t, 2.35, 2.85);
      const resEl = document.getElementById('izu-result');
      if (uRes <= 0) {
        resEl.setAttribute('opacity', '0');
      } else {
        const s = lerp(0.8, 1.0, easeOutBack(uRes));
        resEl.setAttribute('opacity', String(easeOutCubic(uRes)));
        resEl.setAttribute('transform', 'translate(325, 195) scale(' + s + ') translate(-325, -195)');
      }
    };
  </script>
</body>
</html>`;
}

function buildHtmlHydrothermal() {
  return `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: ${WIDTH}px;
    height: ${HEIGHT}px;
    overflow: hidden;
    background: rgba(11, 15, 25, 0.94);
    font-family: "Noto Sans CJK JP", "Hiragino Sans", sans-serif;
    color: #f8fafc;
    border: 1.5px solid rgba(249, 115, 22, 0.4);
    border-radius: 14px;
    padding: 20px 24px 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .header {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .kicker {
    font-size: 16px;
    font-weight: 700;
    color: #f97316;
    letter-spacing: 0.04em;
  }
  .title {
    font-size: 25px;
    font-weight: 900;
    line-height: 1.25;
    border-left: 5px solid #facc15;
    padding-left: 12px;
  }
  .stage {
    position: relative;
    width: 100%;
    height: 390px;
  }
  svg {
    width: 100%;
    height: 100%;
    display: block;
  }
  .credit {
    font-size: 13px;
    color: #94a3b8;
    text-align: right;
  }
</style>
</head>
<body>
  <div class="header" id="header">
    <div class="kicker">第1章B：マグマの熱水循環（金と温泉の共通の起源）</div>
    <div class="title">地下の「熱水」が浅い層に金鉱脈、地表に温泉を作った</div>
  </div>
  <div class="stage">
    <svg viewBox="0 0 812 390">
      <defs>
        <linearGradient id="magmaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#f97316" stop-opacity="0.9" />
          <stop offset="100%" stop-color="#991b1b" stop-opacity="0.95" />
        </linearGradient>
        <linearGradient id="hotArrowGrad" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stop-color="#ef4444" />
          <stop offset="55%" stop-color="#f97316" />
          <stop offset="100%" stop-color="#facc15" />
        </linearGradient>
      </defs>

      <!-- Geological layers -->
      <g id="layers">
        <rect x="20" y="72" width="772" height="92" rx="6" fill="#1e293b" stroke="#475569" stroke-width="1.5" />
        <rect x="20" y="168" width="772" height="118" rx="6" fill="#0f172a" stroke="#334155" stroke-width="1.5" />
        <line x1="20" y1="72" x2="792" y2="72" stroke="#22c55e" stroke-width="4" />
        <text x="36" y="56" fill="#86efac" font-size="16" font-weight="900">地表（温泉が湧く）</text>
        <text x="36" y="96" fill="#94a3b8" font-size="15" font-weight="700">浅い地下層</text>
        <text x="36" y="198" fill="#64748b" font-size="15" font-weight="700">深い地下層</text>
      </g>

      <!-- Magma chamber -->
      <g id="magma">
        <path d="M 190,372 Q 250,278 406,278 Q 562,278 622,372 Z" fill="url(#magmaGrad)" stroke="#fb923c" stroke-width="3" />
        <text x="406" y="346" text-anchor="middle" fill="#fef08a" font-size="22" font-weight="900">マグマ溜まり（熱源）</text>
      </g>

      <!-- Cold water seeping down (Left) -->
      <g id="cold-flow">
        <path id="cold-line" d="M 185,48 L 185,220 Q 185,268 250,288" fill="none" stroke="#38bdf8" stroke-width="7" stroke-linecap="round" />
        <polygon id="cold-head" points="264,292 238,274 244,298" fill="#38bdf8" opacity="0" />
        <text id="cold-label" x="165" y="140" text-anchor="end" fill="#7dd3fc" font-size="16" font-weight="900">雨水・海水の浸透</text>
      </g>

      <!-- Hot hydrothermal water rising (Center & Right) -->
      <g id="hot-flow">
        <path id="hot-line-gold" d="M 406,274 L 406,154" fill="none" stroke="url(#hotArrowGrad)" stroke-width="9" stroke-linecap="round" />
        <polygon id="hot-head-gold" points="406,136 391,160 421,160" fill="#facc15" opacity="0" />

        <path id="hot-line-onsen" d="M 445,274 Q 560,210 595,88" fill="none" stroke="url(#hotArrowGrad)" stroke-width="8" stroke-linecap="round" />
        <polygon id="hot-head-onsen" points="600,68 581,93 608,100" fill="#fb923c" opacity="0" />

        <text id="hot-label" x="424" y="232" fill="#fdba74" font-size="17" font-weight="900">熱水の上昇</text>
        <text id="hot-sub" x="424" y="253" fill="#fde047" font-size="14" font-weight="700">（金などを溶かして運ぶ）</text>
      </g>

      <!-- Gold Vein result -->
      <g id="gold-result">
        <rect x="262" y="76" width="288" height="58" rx="8" fill="rgba(15, 23, 42, 0.92)" stroke="#facc15" stroke-width="2.5" />
        <circle cx="288" cy="105" r="9" fill="#facc15" />
        <text x="422" y="101" text-anchor="middle" fill="#fde047" font-size="19" font-weight="900">金鉱脈（土肥・大仁など）</text>
        <text x="422" y="124" text-anchor="middle" fill="#f8fafc" font-size="13" font-weight="700">浅い層で冷えて金が沈殿</text>
      </g>

      <!-- Onsen result -->
      <g id="onsen-result">
        <rect x="520" y="12" width="252" height="56" rx="8" fill="rgba(15, 23, 42, 0.9)" stroke="#f43f5e" stroke-width="2.5" />
        <text x="646" y="36" text-anchor="middle" fill="#fda4af" font-size="21" font-weight="900">♨ 温泉が湧出</text>
        <text x="646" y="57" text-anchor="middle" fill="#f8fafc" font-size="13" font-weight="700">地表付近まで熱水が到達</text>
      </g>
    </svg>
  </div>
  <div class="credit">模式図：産総研・伊豆半島ジオパーク資料をもとに作成</div>

  <script>
    const clamp01 = (x) => Math.max(0, Math.min(1, x));
    const progress = (t, t0, t1) => t1 <= t0 ? (t >= t1 ? 1 : 0) : clamp01((t - t0) / (t1 - t0));
    const easeOutCubic = (u) => 1 - Math.pow(1 - u, 3);
    const easeInOutCubic = (u) => u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
    const easeOutBack = (x) => {
      const c1 = 1.70158;
      const c3 = c1 + 1;
      return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
    };
    const lerp = (a, b, u) => a + (b - a) * u;

    const coldLine = document.getElementById('cold-line');
    const coldLen = coldLine.getTotalLength();
    coldLine.style.strokeDasharray = String(coldLen);

    const hotGold = document.getElementById('hot-line-gold');
    const hotGoldLen = hotGold.getTotalLength();
    hotGold.style.strokeDasharray = String(hotGoldLen);

    const hotOnsen = document.getElementById('hot-line-onsen');
    const hotOnsenLen = hotOnsen.getTotalLength();
    hotOnsen.style.strokeDasharray = String(hotOnsenLen);

    window.__setTime = (t) => {
      // 0.00 - 0.35s: Stage & geological layers
      const uStage = easeOutCubic(progress(t, 0.0, 0.35));
      document.getElementById('header').style.opacity = String(uStage);
      document.getElementById('layers').setAttribute('opacity', String(uStage));

      // 0.35 - 0.75s: Magma chamber rises
      const uMagma = easeOutCubic(progress(t, 0.35, 0.75));
      const magmaEl = document.getElementById('magma');
      magmaEl.setAttribute('opacity', String(uMagma));
      magmaEl.setAttribute('transform', 'translate(0, ' + lerp(25, 0, uMagma) + ')');

      // 0.75 - 1.55s: Cold water seeps down
      const uCold = easeInOutCubic(progress(t, 0.75, 1.55));
      coldLine.style.strokeDashoffset = String(coldLen * (1 - uCold));
      document.getElementById('cold-label').setAttribute('opacity', String(easeOutCubic(progress(t, 0.75, 1.15))));
      document.getElementById('cold-head').setAttribute('opacity', uCold > 0.88 ? String(clamp01((uCold - 0.88) / 0.12)) : '0');

      // 1.55 - 2.45s: Hot hydrothermal water rises (both branches)
      const uHot = easeInOutCubic(progress(t, 1.55, 2.45));
      hotGold.style.strokeDashoffset = String(hotGoldLen * (1 - uHot));
      hotOnsen.style.strokeDashoffset = String(hotOnsenLen * (1 - uHot));
      const uHotLabel = easeOutCubic(progress(t, 1.65, 2.05));
      document.getElementById('hot-label').setAttribute('opacity', String(uHotLabel));
      document.getElementById('hot-sub').setAttribute('opacity', String(uHotLabel));
      document.getElementById('hot-head-gold').setAttribute('opacity', uHot > 0.85 ? String(clamp01((uHot - 0.85) / 0.15)) : '0');
      document.getElementById('hot-head-onsen').setAttribute('opacity', uHot > 0.85 ? String(clamp01((uHot - 0.85) / 0.15)) : '0');

      // 2.45 - 2.95s: Gold vein pops in
      const uGold = progress(t, 2.45, 2.95);
      const goldEl = document.getElementById('gold-result');
      if (uGold <= 0) {
        goldEl.setAttribute('opacity', '0');
      } else {
        const s = lerp(0.85, 1.0, easeOutBack(uGold));
        goldEl.setAttribute('opacity', String(easeOutCubic(uGold)));
        goldEl.setAttribute('transform', 'translate(406, 105) scale(' + s + ') translate(-406, -105)');
      }

      // 2.65 - 3.15s (0.2s stagger): Onsen result pops in
      const uOnsen = progress(t, 2.65, 3.15);
      const onsenEl = document.getElementById('onsen-result');
      if (uOnsen <= 0) {
        onsenEl.setAttribute('opacity', '0');
      } else {
        const s = lerp(0.85, 1.0, easeOutBack(uOnsen));
        onsenEl.setAttribute('opacity', String(easeOutCubic(uOnsen)));
        onsenEl.setAttribute('transform', 'translate(646, 40) scale(' + s + ') translate(-646, -40)');
      }
    };
  </script>
</body>
</html>`;
}

async function renderDiagram(browser, name, html) {
  const dir = path.join(outBase, name);
  const framesDir = path.join(dir, 'frames');
  fs.mkdirSync(framesDir, { recursive: true });

  const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT } });
  await page.setContent(html, { waitUntil: 'load' });

  for (let i = 0; i < TOTAL_FRAMES; i++) {
    const t = i / FPS;
    await page.evaluate((sec) => window.__setTime(sec), t);
    const framePath = path.join(framesDir, String(i).padStart(5, '0') + '.png');
    await page.screenshot({ path: framePath, type: 'png' });
  }
  await page.close();

  const mp4Path = path.join(outBase, `${name}.mp4`);
  execFileSync('ffmpeg', [
    '-y',
    '-framerate', String(FPS),
    '-i', path.join(framesDir, '%05d.png'),
    '-c:v', 'libx264',
    '-pix_fmt', 'yuv420p',
    '-crf', '18',
    mp4Path,
  ], { stdio: 'inherit' });

  // Contact sheet (6 keyframes: t=0.4, 1.0, 1.6, 2.2, 2.8, 3.5)
  const sheetPath = path.join(outBase, `${name}_sheet.jpg`);
  const picks = [12, 30, 48, 66, 84, 105].map((f) => path.join(framesDir, String(f).padStart(5, '0') + '.png'));
  execFileSync('ffmpeg', [
    '-y',
    ...picks.flatMap((p) => ['-i', p]),
    '-filter_complex', 'hstack=inputs=3[top];[3:v][4:v][5:v]hstack=inputs=3[bot];[top][bot]vstack=inputs=2,scale=1920:-1',
    '-q:v', '2',
    sheetPath,
  ], { stdio: 'inherit' });

  console.log(`Rendered ${mp4Path} and ${sheetPath}`);
}

const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=metal'],
});

try {
  await renderDiagram(browser, 'plate_collision_motion', buildHtmlPlateCollision());
  await renderDiagram(browser, 'hydrothermal_motion', buildHtmlHydrothermal());
} finally {
  await browser.close();
}
