import { lerpRect, panelExpandProgress } from '../overlay-position.js';
import { blinkAt, chartGeometry, ease, easeOutBack, mouthOpenAt, reactionAt } from '../lib.js';
import { countValue, counterNumber, odometerColumns } from '../counter.js';
import type { ChartOverlay, CounterOverlay, Overlay, ReactionOverlay } from '../types.js';
import { clamp01, el, esc, type Inn, outCubic, ov, type Phase, scale } from './overlay-dom.js';

type PhotoMarkerOverlay = Extract<Overlay, { type: 'photo_marker' }>;
type PanelOverlay = Extract<Overlay, { type: 'panel' }>;

/** Photo card with a connector to the place it shows (and where it was taken from). */
export function drawPhotoMarker(o: PhotoMarkerOverlay, inn: Inn, out: number): void {
  const [x, y] = o.screen ?? [80, 80];
  const w = o.width ?? 750;
  const h = o.height ?? 590;
  const target = ov.map.project(o.at);
  const tx = target.x / scale();
  const ty = target.y / scale();
  const camera = o.cameraAt ? ov.map.project(o.cameraAt) : null;
  const cx = camera ? camera.x / scale() : 0;
  const cy = camera ? camera.y / scale() : 0;
  const [cameraDx, cameraDy] = o.cameraLabelOffset ?? [-20, -16];
  const bridge = o.bridgeAt ? ov.map.project(o.bridgeAt) : null;
  const bx = bridge ? bridge.x / scale() : 0;
  const by = bridge ? bridge.y / scale() : 0;
  const sx = x + w;
  const sy = y + h * 0.58;
  const mx = sx + (tx - sx) * 0.42;
  const marker =
    `<circle cx="${tx}" cy="${ty}" r="15" fill="#ffbf45" stroke="#172338" stroke-width="5"/>` +
    `<text x="${tx + 24}" y="${ty + 8}" class="marker-label">${esc(o.targetLabel ?? '')}</text>`;
  const shotMarker = camera
    ? `<circle cx="${cx}" cy="${cy}" r="9" fill="#67e1dc" stroke="#172338" stroke-width="4"/>` +
      `<text x="${cx + cameraDx}" y="${cy + cameraDy}" text-anchor="${o.cameraLabelAnchor === 'start' ? 'start' : 'end'}" class="marker-label small">${esc(o.cameraLabel ?? '')}</text>`
    : '';
  const bridgeMarker = bridge
    ? `<circle cx="${bx}" cy="${by}" r="8" fill="#f6a8ff" stroke="#172338" stroke-width="4"/>` +
      `<text x="${bx + 18}" y="${by - 55}" class="marker-label small">${esc(o.bridgeLabel ?? '')}</text>`
    : '';
  el(
    'photo-connector',
    `<svg viewBox="0 0 1920 1080"><path d="M ${sx} ${sy} L ${mx} ${sy} L ${tx} ${ty}" class="connector"/>${marker}${shotMarker}${bridgeMarker}</svg>`,
    { left: '0px', top: '0px', opacity: inn(0.25) * out },
  );
  el(
    'photo-marker-card',
    `<div class="photo-caption">${esc(o.caption ?? '')}</div>` +
      `<img src="/${esc(o.src.replace(/^\/+/, ''))}"><div class="photo-credit">${esc(o.credit ?? '')}</div>`,
    { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px', opacity: inn(0.25) * out },
  );
}

/** Picture panel: a card that wipes in, or grows to the whole frame (fullscreen, expand/collapse). */
export function drawPanel(o: PanelOverlay, ph: Phase, t: number, inn: Inn, out: number): void {
  const [x, y] = o.screen ?? [1090, 150];
  const wipe = 100 * (1 - outCubic(inn(0.55)));
  const [start, end] = o.show ?? [0, 1];
  const p = clamp01((t - start) / Math.max(0.001, end - start));
  const zoom =
    o.motion === 'still'
      ? 1
      : o.motion === 'out'
        ? 1.1 - 0.08 * p
        : o.motion === 'in'
          ? 1.02 + 0.08 * p
          : 1.06 - 0.06 * outCubic(inn(1.2)) + 0.03 * clamp01(ph.since / 12);
  const shiftY = o.motion === 'up' ? 12 - 24 * p : o.motion === 'down' ? -12 + 24 * p : 0;
  const imgSrc = `/${esc(o.src.replace(/^\/+/, ''))}`;
  if (o.fullscreen || o.expand) {
    const exp = o.fullscreen ? 1 : ease('inOut', panelExpandProgress(o.expand, t, o.collapse));
    const startW = o.width ?? 480;
    const startH = o.height ?? Math.round(startW * 0.72);
    const rect = lerpRect({ x, y, w: startW, h: startH }, { x: 0, y: 0, w: 1920, h: 1080 }, exp);
    const padX = Math.round(14 + 34 * exp);
    const padTop = Math.round(56 + 36 * exp);
    const padBot = Math.round(36 + 32 * exp);
    const capSize = Math.round(22 + 12 * exp);
    const crSize = Math.round(16 + 5 * exp);
    const radius = Math.round(14 * (1 - exp));
    el(
      'panel-fullscreen',
      `<img src="${imgSrc}" style="position:absolute;inset:-40px;width:calc(100% + 80px);height:calc(100% + 80px);object-fit:cover;filter:blur(32px) brightness(0.32);opacity:${exp};pointer-events:none">` +
        `<div style="position:absolute;left:${padX}px;right:${padX}px;top:${padTop}px;bottom:${padBot}px;display:flex;align-items:center;justify-content:center;overflow:hidden">` +
        `<img src="${imgSrc}" style="max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;box-shadow:0 20px 56px rgba(0,0,0,0.7);transform:translateY(${shiftY}px) scale(${zoom})"></div>` +
        (o.caption
          ? `<div style="position:absolute;left:0;right:0;top:0;padding:${Math.round(14 + 12 * exp)}px ${Math.round(18 + 36 * exp)}px;background:linear-gradient(180deg,rgba(8,14,24,0.88),rgba(8,14,24,0));color:#f5f8ff;font-size:${capSize}px;font-weight:700;letter-spacing:0.02em;text-shadow:0 2px 10px rgba(0,0,0,0.75);opacity:${inn(0.3, 0.15)}">${esc(o.caption)}</div>`
          : '') +
        (o.credit
          ? `<div style="position:absolute;right:${Math.round(16 + 32 * exp)}px;bottom:${Math.round(10 + 8 * exp)}px;color:rgba(230,238,250,0.86);font-size:${crSize}px;text-shadow:0 1px 6px rgba(0,0,0,0.85);opacity:${inn(0.3, 0.25)}">${esc(o.credit)}</div>`
          : ''),
      {
        left: rect.x + 'px',
        top: rect.y + 'px',
        width: rect.w + 'px',
        height: rect.h + 'px',
        background: `rgba(11,17,27,${0.92 + 0.08 * exp})`,
        borderRadius: radius + 'px',
        border: exp < 0.99 ? `2px solid rgba(255,255,255,${0.28 * (1 - exp)})` : 'none',
        boxShadow: exp < 0.99 ? `0 18px 44px rgba(0,0,0,${0.65 * (1 - exp)})` : 'none',
        overflow: 'hidden',
        opacity: inn(0.2) * out,
      },
    );
  } else {
    el(
      'panel',
      (o.caption ? `<span class="cap" style="opacity:${inn(0.3, 0.25)}">${esc(o.caption)}</span>` : '') +
        `<span class="frame"><img src="${imgSrc}" style="transform:translateY(${shiftY}px) scale(${zoom})"></span>` +
        (o.credit ? `<span class="cr" style="opacity:${inn(0.3, 0.4)}">${esc(o.credit)}</span>` : ''),
      { left: x + 'px', top: y + 'px', width: (o.width ?? 720) + 'px', opacity: out, clipPath: `inset(0 ${wipe}% 0 0)` },
    );
  }
}

export function drawChart(o: ChartOverlay, ph: { since: number }, inn: Inn, out: number): void {
  const W = o.width ?? 780;
  const H = o.height ?? 430;
  const g = chartGeometry(o.points, { w: W, h: H, pad: [36, 34, 48, 78], ymin: o.ymin, ymax: o.ymax });
  const p = ease('inOut', clamp01((ph.since - 0.5) / (o.drawSec ?? 2.4)));
  const drawn = p * g.length;
  const fmt = (v: number) => `${(+v).toLocaleString('en-US', { maximumFractionDigits: o.decimals ?? 0 })}${o.unit ?? ''}`;
  const ticks = o.yticks ?? [];
  const yOf = (v: number) => g.plot.y + (1 - (v - g.lo) / (g.hi - g.lo)) * g.plot.h;
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><g style="opacity:${inn(0.4, 0.2)}">`;
  for (const v of ticks) {
    svg += `<line x1="${g.plot.x}" x2="${g.plot.x + g.plot.w}" y1="${yOf(v)}" y2="${yOf(v)}" class="grid"/><text x="${g.plot.x - 12}" y="${yOf(v) + 7}" class="ytick">${esc(fmt(v))}</text>`;
  }
  for (const [lab, idx] of o.xlabels ?? []) {
    svg += `<text x="${g.pts[idx]![0]}" y="${H - 12}" class="xtick">${esc(lab)}</text>`;
  }
  svg += `</g><path d="M${g.pts.map((q) => q.map((v) => v.toFixed(1)).join(',')).join('L')}" class="line" style="stroke-dasharray:${g.length};stroke-dashoffset:${g.length - drawn}"/>`;
  g.pts.forEach((q, i) => {
    const reach = p >= 1 ? ph.since - 0.5 - (o.drawSec ?? 2.4) + 0.34 : ((drawn - g.cum[i]!) / 300) * 3;
    if (drawn < g.cum[i]! - 1e-6) return;
    const v = clamp01(reach * 3);
    const k = 0.4 + 0.6 * easeOutBack(v);
    const since = v / 3;
    svg += `<circle cx="${q[0]}" cy="${q[1]}" r="${7 * k}" class="pt"/>`;
    if ((o.labels ?? []).includes(i)) {
      svg += `<text x="${q[0]}" y="${q[1] - 18}" class="val" style="opacity:${clamp01(since * 3)}">${esc(fmt(o.points[i]![1]))}</text>`;
    }
  });
  if (p >= 1) {
    const last = g.pts[g.pts.length - 1]!;
    const r = (ph.since % 1.4) / 1.4;
    svg += `<circle cx="${last[0]}" cy="${last[1]}" r="${8 + r * 22}" class="pulse" style="opacity:${(1 - r) * 0.7}"/>`;
  }
  svg += '</svg>';
  const [x, y] = o.screen ?? [1090, 150];
  el(
    'chart',
    (o.caption ? `<span class="cap" style="opacity:${inn(0.3, 0.2)}">${esc(o.caption)}</span>` : '') +
      svg +
      (o.credit ? `<span class="cr" style="opacity:${inn(0.3, 0.4)}">${esc(o.credit)}</span>` : ''),
    { left: x + 'px', top: y + 'px', width: W + 'px', opacity: out, clipPath: `inset(0 ${100 * (1 - outCubic(inn(0.55)))}% 0 0)` },
  );
}

export function drawReaction(o: ReactionOverlay, since: number): void {
  const cfg = ov.spec.reaction!;
  const chars = cfg.characters ?? {};
  const r = reactionAt(o.segs, since);
  const order = cfg.order ?? Object.keys(chars);
  const h = cfg.height ?? 300;
  const fps = ov.spec.fps ?? 30;
  let html = '';
  for (const key of order) {
    const c = chars[key];
    if (!c) continue;
    const speaking = !!(r && r.seg.speaker === key);
    const face = speaking ? r!.seg.face : r ? r.seg.react : 'normal';
    const mouth = speaking && mouthOpenAt(r!.seg.env, r!.since, fps) ? 'o' : 'c';
    const eyes = blinkAt(ov.nowSec, c.seed ?? key) ? 'c' : 'o';
    const hop = speaking ? Math.sin(Math.PI * clamp01(r!.since / 0.28)) * 12 : 0;
    const k = speaking || !r ? 1 : 0.9;
    html +=
      `<img src="/${esc(c.sprites.replace(/^\/+|\/+$/g, ''))}/${face}_${eyes}_${mouth}.png" style="height:${h}px;` +
      `transform:translateY(${-hop}px) scale(${k});filter:drop-shadow(0 4px 10px rgba(0,0,0,0.5))${speaking || !r ? '' : ' brightness(0.72) saturate(0.8)'}">`;
  }
  const side = cfg.side ?? 'right';
  el('reaction', html, { [side]: (cfg.margin ?? 16) + 'px', bottom: (cfg.bottom ?? 150) + 'px' });
}

/** Odometer wheels for a rolling counter; leading wheels fade in as the number reaches them. */
export function rollingDigits(o: CounterOverlay, t: number): string {
  const value = counterNumber(o, t);
  if (value === null) return countValue(o, t);
  const final = Math.max(1, Math.round(Math.abs(Number(o.value))));
  const digits = String(final).length;
  const columns = odometerColumns(value, digits);
  const strip = '0123456789'.split('').concat('0').join('<br>');
  let html = '';
  columns.forEach((pos, i) => {
    const place = digits - 1 - i;
    // a wheel appears only as the number reaches its place (no leading zeros)
    const shown = place === 0 ? 1 : Math.min(1, Math.max(0, (value / 10 ** place - 0.97) / 0.03));
    html += `<span class="wheel" style="opacity:${shown.toFixed(3)}"><span class="strip" style="transform:translateY(${(-pos).toFixed(4)}em)">${strip}</span></span>`;
    if (place > 0 && place % 3 === 0 && (o.grouping ?? true)) html += `<span class="sep" style="opacity:${shown.toFixed(3)}">,</span>`;
  });
  return html;
}
