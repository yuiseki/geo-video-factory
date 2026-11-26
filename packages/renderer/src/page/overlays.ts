import { hasFullscreenPanel, labelAccent, labelPosition, panelExpandProgress } from '../overlay-position.js';
import { choroplethDimMultiplier, choroplethHeightExpression } from '../choropleth.js';
import { choroplethRiseProgress, drawChoroplethLabels, drawChoroplethLegend } from './choropleth-dom.js';
import { ease, easeOutBack, fadeAlpha, phase, sliceLine, typeCount } from '../lib.js';
import { countValue } from '../counter.js';
import type { LngLat, Overlay, Shot } from '../types.js';
import { clamp01, el, esc, type Inn, outCubic, ov, type Phase, scale } from './overlay-dom.js';
import { drawChart, drawPanel, drawPhotoMarker, drawReaction, rollingDigits } from './overlay-widgets.js';

export { configureOverlayRenderer, setOverlayTime } from './overlay-dom.js';

export function drawOverlays(si: number, shot: Shot, t: number, pass: 'map' | 'dom'): void {
  if (pass === 'dom') ov.overlayEl.textContent = '';
  if (pass === 'map') {
    ov.spec.shots.forEach((s, i) =>
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
        ids.forEach((lid) => ov.map.setLayoutProperty(lid, 'visibility', i === si ? 'visible' : 'none'));
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
        if (o.labelProperty) drawChoroplethLabels(o, t, a, ov.map, scale(), el, esc);
        if (o.legend) drawChoroplethLegend(o, a, hasSub, el, esc);
      }
      return;
    }
    if (o.type === 'base' || o.type === 'image') {
      ov.map.setPaintProperty(id, 'raster-opacity', a);
    } else if (o.type === 'heatmap') {
      ov.map.setPaintProperty(id, 'heatmap-opacity', a * (o.opacity ?? 0.85));
    } else if (o.type === 'line') {
      const frac = o.draw ? Math.min(1, Math.max(0, (t - o.draw[0]) / (o.draw[1] - o.draw[0]))) : 1;
      ov.map.getSource(id).setData({ type: 'Feature', geometry: { type: 'LineString', coordinates: sliceLine(o.coords, frac) } });
      ov.map.setPaintProperty(id, 'line-opacity', a);
      ov.map.setPaintProperty(id + '-casing', 'line-opacity', a * 0.9);
    } else if (o.type === 'polygon') {
      ov.map.setPaintProperty(id, 'line-opacity', a);
      ov.map.setPaintProperty(id + '-fill', 'fill-opacity', a * (o.fillOpacity ?? 0.35));
    } else if (o.type === 'choropleth') {
      const dim = o.focus ? choroplethDimMultiplier(t, o.focus.window, o.focus.dimOpacity) : 1;
      const variants = o.focus ? [{ suffix: '', mult: dim }, { suffix: '-focus', mult: 1 }] : [{ suffix: '', mult: 1 }];
      const progress = o.extrude && o.rise ? choroplethRiseProgress(o, t) : null;
      for (const { suffix, mult } of variants) {
        const lid = id + suffix;
        ov.map.setPaintProperty(lid, 'line-opacity', a * mult);
        if (o.extrude) {
          ov.map.setPaintProperty(lid + '-fill', 'fill-extrusion-opacity', a * mult * (o.opacity ?? 0.85));
          if (progress !== null) {
            ov.map.setPaintProperty(
              lid + '-fill',
              'fill-extrusion-height',
              choroplethHeightExpression(o.heightProperty ?? o.property, o.heightScale ?? 1, o.heightBase ?? 0, progress),
            );
          }
        } else {
          ov.map.setPaintProperty(lid + '-fill', 'fill-opacity', a * mult * (o.opacity ?? 0.78));
        }
      }
    } else {
      drawMotion(o, phase(o.show, t, shot.duration ?? 0), t, a, (v) => {
        tint = Math.max(tint, v);
      });
    }
  });
  ov.tintEl.style.opacity = String(tint);
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
    const left = !!ov.spec.reaction && (ov.spec.reaction.side ?? 'right') === 'right';
    Object.assign(
      credit.style,
      left ? { left: '24px', right: 'auto', textAlign: 'left' } : { left: 'auto', right: '24px', textAlign: 'right' },
    );
  }
}

function drawMotion(o: Overlay, ph: Phase, t: number, a: number, setTint: (v: number) => void): void {
  if (!ph.on) {
    if (o.type === 'chapter') setTint(0);
    return;
  }
  const inn: Inn = (dur: number, delay = 0) => clamp01((ph.since - delay) / dur);
  const out = clamp01(ph.until / 0.3);
  const leave = 1 - out;
  const pos = (item: { at?: LngLat; screen?: [number, number] }) => {
    if (item.at) {
      const p = ov.map.project(item.at);
      return { left: p.x / scale() + 'px', top: p.y / scale() + 'px' };
    }
    return { left: (item.screen?.[0] ?? 70) + 'px', top: (item.screen?.[1] ?? 160) + 'px' };
  };

  if (o.type === 'label') {
    const labelPos = o.at ? labelPosition(ov.map.project(o.at), scale(), o.offset) : pos(o);
    const accent = labelAccent(o.color);
    if (o.leader && o.at) {
      const point = ov.map.project(o.at);
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
    drawPhotoMarker(o, inn, out);
  } else if (o.type === 'panel') {
    drawPanel(o, ph, t, inn, out);
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
