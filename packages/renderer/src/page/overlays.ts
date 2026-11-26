import { hasFullscreenPanel, labelAccent, labelPosition, lerpRect, panelExpandProgress } from '../overlay-position.js';
import { choroplethDimMultiplier, choroplethHeightExpression } from '../choropleth.js';
import { choroplethRiseProgress, drawChoroplethLabels, drawChoroplethLegend } from './choropleth-dom.js';
import {
  blinkAt,
  chartGeometry,
  ease,
  easeOutBack,
  fadeAlpha,
  mouthOpenAt,
  phase,
  reactionAt,
  sliceLine,
  typeCount,
} from '../lib.js';
import { countValue, counterNumber, odometerColumns } from '../counter.js';
import type { ChartOverlay, CounterOverlay, LngLat, Overlay, ReactionOverlay, Shot, ShotSpec } from '../types.js';
import type { MapLibreMap } from './map-types.js';

let map: MapLibreMap;
let spec: ShotSpec;
let overlayEl: HTMLElement;
let tintEl: HTMLElement;
let nowSec = 0;

export function configureOverlayRenderer(context: {
  map: MapLibreMap;
  spec: ShotSpec;
  overlayEl: HTMLElement;
  tintEl: HTMLElement;
}): void {
  ({ map, spec, overlayEl, tintEl } = context);
}

export function setOverlayTime(sec: number): void {
  nowSec = sec;
}

const scale = () => (spec.width ?? 1920) / 1920;

function el(cls: string, html: string, style: Record<string, string | number> = {}): HTMLDivElement {
  const d = document.createElement('div');
  d.className = 'o ' + cls;
  d.innerHTML = html;
  Object.assign(d.style, style);
  overlayEl.appendChild(d);
  return d;
}

const esc = (s: string) =>
  String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c] ?? c));

export function drawOverlays(si: number, shot: Shot, t: number, pass: 'map' | 'dom'): void {
  if (pass === 'dom') overlayEl.textContent = '';
  if (pass === 'map') {
    spec.shots.forEach((s, i) =>
      (s.overlays || []).forEach((o, oi) => {
        if (!['line', 'polygon', 'choropleth', 'heatmap', 'base', 'image'].includes(o.type)) return;
        const id = `ov-${i}-${oi}`;
        const ids =
          o.type === 'line'
            ? [id, id + '-casing']
            : o.type === 'polygon'
              ? [id, id + '-fill']
              : o.type === 'choropleth'
                ? o.focus
                  ? [id, id + '-fill', id + '-focus', id + '-focus-fill']
                  : [id, id + '-fill']
                : [id];
        ids.forEach((lid) => map.setLayoutProperty(lid, 'visibility', i === si ? 'visible' : 'none'));
      }),
    );
  }
  let tint = shot.tint ?? 0;
  const hasSub = (shot.overlays || []).some((o) => o.type === 'subtitle');
  (shot.overlays || []).forEach((o, oi) => {
    const a = fadeAlpha(o.show, t, o.fade ?? 0.06);
    const id = `ov-${si}-${oi}`;
    const isMap = ['line', 'polygon', 'choropleth', 'heatmap', 'base', 'image'].includes(o.type);
    if (isMap !== (pass === 'map')) {
      if (o.type === 'chapter' && pass === 'map') tint = Math.max(tint, 0.55 * a);
      if (o.type === 'choropleth' && pass === 'dom' && a > 0) {
        if (o.labelProperty) drawChoroplethLabels(o, t, a, map, scale(), el, esc);
        if (o.legend) drawChoroplethLegend(o, a, hasSub, el, esc);
      }
      return;
    }
    if (o.type === 'base' || o.type === 'image') {
      map.setPaintProperty(id, 'raster-opacity', a);
    } else if (o.type === 'heatmap') {
      map.setPaintProperty(id, 'heatmap-opacity', a * (o.opacity ?? 0.85));
    } else if (o.type === 'line') {
      const frac = o.draw ? Math.min(1, Math.max(0, (t - o.draw[0]) / (o.draw[1] - o.draw[0]))) : 1;
      map.getSource(id).setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: sliceLine(o.coords, frac) } });
      map.setPaintProperty(id, 'line-opacity', a);
      map.setPaintProperty(id + '-casing', 'line-opacity', a * 0.9);
    } else if (o.type === 'polygon') {
      map.setPaintProperty(id, 'line-opacity', a);
      map.setPaintProperty(id + '-fill', 'fill-opacity', a * (o.fillOpacity ?? 0.35));
    } else if (o.type === 'choropleth') {
      const dim = o.focus ? choroplethDimMultiplier(t, o.focus.window, o.focus.dimOpacity) : 1;
      const variants = o.focus ? [{ suffix: '', mult: dim }, { suffix: '-focus', mult: 1 }] : [{ suffix: '', mult: 1 }];
      const progress = o.extrude && o.rise ? choroplethRiseProgress(o, t) : null;
      for (const { suffix, mult } of variants) {
        const lid = id + suffix;
        map.setPaintProperty(lid, 'line-opacity', a * mult);
        if (o.extrude) {
          map.setPaintProperty(lid + '-fill', 'fill-extrusion-opacity', a * mult * (o.opacity ?? 0.85));
          if (progress !== null) {
            map.setPaintProperty(
              lid + '-fill',
              'fill-extrusion-height',
              choroplethHeightExpression(o.heightProperty ?? o.property, o.heightScale ?? 1, o.heightBase ?? 0, progress),
            );
          }
        } else {
          map.setPaintProperty(lid + '-fill', 'fill-opacity', a * mult * (o.opacity ?? 0.78));
        }
      }
    } else {
      drawMotion(o, phase(o.show, t, shot.duration ?? 0), t, a, (v) => {
        tint = Math.max(tint, v);
      });
    }
  });
  tintEl.style.opacity = String(tint);
  if (pass === 'dom') {
    const hasSub = (shot.overlays || []).some((o) => o.type === 'subtitle');
    const maxExpand = (shot.overlays || []).reduce((m, o) => {
      if (o.type === 'panel' && o.fullscreen) return 1;
      if (o.type === 'panel' && o.expand) return Math.max(m, ease('inOut', panelExpandProgress(o.expand, t, o.collapse)));
      return m;
    }, 0);
    const hideMapCredit = hasFullscreenPanel(shot.overlays || []) || maxExpand >= 0.99;
    const credit = document.getElementById('credit')!;
    credit.style.display = hideMapCredit ? 'none' : '';
    credit.style.opacity = hideMapCredit ? '0' : String(1 - maxExpand);
    credit.style.bottom = hasSub ? '196px' : '16px';
    const left = !!spec.reaction && (spec.reaction.side ?? 'right') === 'right';
    Object.assign(
      credit.style,
      left ? { left: '24px', right: 'auto', textAlign: 'left' } : { left: 'auto', right: '24px', textAlign: 'right' },
    );
  }
}

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
const outCubic = (x: number) => ease('out', x);

function drawMotion(o: Overlay, ph: { since: number; until: number; on: boolean }, t: number, a: number, setTint: (v: number) => void): void {
  if (!ph.on) {
    if (o.type === 'chapter') setTint(0);
    return;
  }
  const inn = (dur: number, delay = 0) => clamp01((ph.since - delay) / dur);
  const out = clamp01(ph.until / 0.3);
  const leave = 1 - out;
  const pos = (item: { at?: LngLat; screen?: [number, number] }) => {
    if (item.at) {
      const p = map.project(item.at);
      return { left: p.x / scale() + 'px', top: p.y / scale() + 'px' };
    }
    return { left: (item.screen?.[0] ?? 70) + 'px', top: (item.screen?.[1] ?? 160) + 'px' };
  };

  if (o.type === 'label') {
    const labelPos = o.at ? labelPosition(map.project(o.at), scale(), o.offset) : pos(o);
    const accent = labelAccent(o.color);
    if (o.leader && o.at) {
      const point = map.project(o.at);
      const x = point.x / scale();
      const y = point.y / scale();
      const dx = o.offset?.[0] ?? 0;
      const dy = o.offset?.[1] ?? 0;
      const endY = y + dy + (dy < 0 ? 18 : -18);
      el('leader', `<svg width="1920" height="1080" style="overflow:visible;pointer-events:none"><path d="M${x},${y} L${x + dx},${endY}" stroke="#182338" stroke-width="7" fill="none"/><path d="M${x},${y} L${x + dx},${endY}" stroke="${esc(accent.leaderStroke)}" stroke-width="3" fill="none"/><circle cx="${x}" cy="${y}" r="7" fill="${esc(accent.leaderStroke)}" stroke="#182338" stroke-width="3"/></svg>`, { left: '0px', top: '0px', opacity: inn(0.15) * out, pointerEvents: 'none' });
    }
    if (o.style === 'tag') {
      const k = 0.5 + 0.5 * easeOutBack(inn(0.45));
      el('label tag', esc(o.text), { ...labelPos, ...accent.tagStyle, opacity: inn(0.15) * out, transform: `translate(-50%, -50%) scale(${k})` });
    } else {
      const ring = (ph.since % 1.6) / 1.6;
      const reveal = 100 * (1 - outCubic(inn(0.5, 0.15)));
      el(
        'label',
        (o.dot ? `<span class="dot"><span class="ring" style="transform:scale(${1 + ring * 2.2});opacity:${(1 - ring) * 0.8}"></span></span>` : '') +
          `<span class="txt" style="clip-path:inset(-20% ${reveal}% -20% 0)">${esc(o.text)}</span>`,
        { ...labelPos, opacity: inn(0.15) * out },
      );
    }
  } else if (o.type === 'counter') {
    const [x, y] = o.screen ?? [70, 160];
    const up = (1 - outCubic(inn(0.45))) * 40;
    const sc = o.scale ?? 1;
    el(
      'counter',
      (o.caption ? `<span class="cap" style="opacity:${inn(0.3, 0.1)}">${esc(o.caption)}</span>` : '') +
        (o.prefix ? `<span class="pre">${esc(o.prefix)}</span>` : '') +
        `<span class="num">${o.roll ? rollingDigits(o, t) : esc(countValue(o, t))}</span>` +
        (o.unit ? `<span class="unit">${esc(o.unit)}</span>` : '') +
        `<span class="rule" style="width:${outCubic(inn(0.5, 0.2)) * 100}%"></span>`,
      { left: x + 'px', top: y + 'px', opacity: inn(0.2) * out, transformOrigin: 'top left', transform: `translateY(${up - leave * 20}px) scale(${sc})` },
    );
  } else if (o.type === 'chapter') {
    setTint(0.55 * inn(0.4) * out);
    const reveal = 100 * (1 - outCubic(inn(0.6, 0.2)));
    el(
      'chapter',
      (o.kicker ? `<span class="kicker" style="letter-spacing:${0.6 - 0.45 * outCubic(inn(0.6))}em;opacity:${inn(0.3)}">${esc(o.kicker)}</span>` : '') +
        `<span class="title" style="clip-path:inset(-20% ${reveal}% -20% 0)">${esc(o.text)}</span>` +
        `<span class="rule" style="width:${outCubic(inn(0.7, 0.1)) * 640}px"></span>`,
      { opacity: out, transform: `translateY(${-leave * 24}px)` },
    );
  } else if (o.type === 'note') {
    el('note', esc(o.text), { opacity: inn(0.3) * out });
  } else if (o.type === 'quote') {
    const [x, y] = o.screen ?? [70, 160];
    const n = typeCount(o.text, Math.max(0, ph.since - 0.35), o.cps ?? 30);
    const chars = [...o.text];
    el(
      'quote' + (o.marks === false ? ' plain' : ''),
      `<span class="bar" style="transform:scaleY(${outCubic(inn(0.35))})"></span>` +
        `<span class="src" style="opacity:${inn(0.3, 0.15)}">${esc(o.source ?? '')}${o.date ? '　' + esc(o.date) : ''}</span>` +
        `<span class="q"><span>${esc(chars.slice(0, n).join(''))}</span><span class="rest">${esc(chars.slice(n).join(''))}</span></span>`,
      {
        left: x + 'px',
        top: y + 'px',
        width: (o.width ?? 760) + 'px',
        opacity: inn(0.25) * out,
        transform: `translateX(${-(1 - outCubic(inn(0.45))) * 80 - leave * 60}px)`,
      },
    );
  } else if (o.type === 'photo_marker') {
    const [x, y] = o.screen ?? [80, 80];
    const w = o.width ?? 750;
    const h = o.height ?? 590;
    const target = map.project(o.at);
    const tx = target.x / scale();
    const ty = target.y / scale();
    const camera = o.cameraAt ? map.project(o.cameraAt) : null;
    const cx = camera ? camera.x / scale() : 0;
    const cy = camera ? camera.y / scale() : 0;
    const [cameraDx, cameraDy] = o.cameraLabelOffset ?? [-20, -16];
    const bridge = o.bridgeAt ? map.project(o.bridgeAt) : null;
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
  } else if (o.type === 'panel') {
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
  } else if (o.type === 'chart') {
    drawChart(o, ph, inn, out);
  } else if (o.type === 'sticker') {
    const k = easeOutBack(inn(0.5));
    const bob = Math.sin(ph.since * 2.2) * 6;
    const tilt = Math.sin(ph.since * 1.4) * 2.5 + (1 - k) * -12;
    el(
      'sticker',
      `<img src="/${esc(o.src.replace(/^\/+/, ''))}">` + (o.credit ? `<span class="cr">${esc(o.credit)}</span>` : ''),
      {
        left: (o.screen?.[0] ?? 1400) + 'px',
        top: (o.screen?.[1] ?? 500) + 'px',
        width: (o.width ?? 320) + 'px',
        opacity: inn(0.15) * out,
        transform: `translateY(${bob}px) rotate(${tilt}deg) scale(${0.3 + 0.7 * k})`,
      },
    );
  } else if (o.type === 'reaction') {
    drawReaction(o, ph.since);
  } else if (o.type === 'subtitle') {
    el('subtitle', esc(o.text), {
      opacity: a,
      ...(o.color ? { color: o.color } : {}),
      transform: `translateY(${(1 - outCubic(inn(0.18))) * 14}px)`,
    });
  }
}

function drawChart(o: ChartOverlay, ph: { since: number }, inn: (d: number, delay?: number) => number, out: number): void {
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

function drawReaction(o: ReactionOverlay, since: number): void {
  const cfg = spec.reaction!;
  const chars = cfg.characters ?? {};
  const r = reactionAt(o.segs, since);
  const order = cfg.order ?? Object.keys(chars);
  const h = cfg.height ?? 300;
  const fps = spec.fps ?? 30;
  let html = '';
  for (const key of order) {
    const c = chars[key];
    if (!c) continue;
    const speaking = !!(r && r.seg.speaker === key);
    const face = speaking ? r!.seg.face : r ? r.seg.react : 'normal';
    const mouth = speaking && mouthOpenAt(r!.seg.env, r!.since, fps) ? 'o' : 'c';
    const eyes = blinkAt(nowSec, c.seed ?? key) ? 'c' : 'o';
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
function rollingDigits(o: CounterOverlay, t: number): string {
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
