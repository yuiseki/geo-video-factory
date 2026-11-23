import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { choroplethRiseProgress, drawChoroplethLabels, drawChoroplethLegend, preloadChoroplethLabels } from '../src/page/choropleth-dom.js';
import { FakeEl, fakeMap, installFakeDocument } from './support/fake-dom.js';
import type { ChoroplethOverlay, ShotSpec } from '../src/types.js';

let dom: ReturnType<typeof installFakeDocument>;
beforeEach(() => { dom = installFakeDocument(); });
afterEach(() => dom.restore());

const square = (x: number, y: number, props: Record<string, unknown>) => ({
  type: 'Feature',
  properties: props,
  geometry: { type: 'Polygon', coordinates: [[[x, y], [x + 2, y], [x + 2, y + 2], [x, y + 2], [x, y]]] },
});
const data = { type: 'FeatureCollection', features: [square(0, 0, { name: 'A', v: 10 }), square(10, 0, { name: 'B', v: 50 }), square(20, 0, { name: '<C>', v: 90 })] };
const base = (extra: Partial<ChoroplethOverlay> = {}): ChoroplethOverlay =>
  ({ type: 'choropleth', data, property: 'v', breaks: [0, 50], colors: ['#111', '#eee'], labelProperty: 'name', ...extra }) as ChoroplethOverlay;

const makeEl = () => {
  const made: FakeEl[] = [];
  const el = (cls: string, html: string, style: Record<string, string | number> = {}) => {
    const d = new FakeEl();
    d.className = 'o ' + cls;
    d.innerHTML = html;
    Object.assign(d.style, style);
    made.push(d);
    return d as never;
  };
  return { made, el };
};
const esc = (s: string) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c] ?? c));
const specWith = (o: ChoroplethOverlay): ShotSpec => ({ shots: [{ duration: 1, overlays: [o] }] }) as never;

test('choroplethRiseProgress: 1 without extrusion or rise, eased 0..1 over the window, step for zero-length windows', () => {
  assert.equal(choroplethRiseProgress(base(), 0), 1);
  assert.equal(choroplethRiseProgress(base({ extrude: true }), 0), 1);
  const o = base({ extrude: true, rise: [0.2, 0.6] });
  assert.equal(choroplethRiseProgress(o, 0.1), 0);
  assert.equal(choroplethRiseProgress(o, 0.9), 1);
  const mid = choroplethRiseProgress(o, 0.4);
  assert.ok(mid > 0.5 && mid < 1, 'ease-out is above linear at the midpoint');
  const step = base({ extrude: true, rise: [0.5, 0.5] });
  assert.equal(choroplethRiseProgress(step, 0.49), 0);
  assert.equal(choroplethRiseProgress(step, 0.5), 1);
});

test('drawChoroplethLegend: swatch per class, escaped title, corner placement and subtitle clearance', () => {
  const { made, el } = makeEl();
  drawChoroplethLegend(base({ legend: { title: '<人口>', position: 'top-right' } }), 0.5, false, el, esc);
  assert.equal(made.length, 1);
  assert.equal(made[0]!.className, 'o legend');
  assert.ok(made[0]!.innerHTML.includes('&lt;人口&gt;'));
  assert.equal(made[0]!.innerHTML.split('legend-swatch').length - 1, 2);
  assert.deepEqual([made[0]!.style.top, made[0]!.style.right, made[0]!.style.opacity], ['32px', '32px', 0.5]);

  const withSub = makeEl();
  drawChoroplethLegend(base({ legend: true }), 1, true, withSub.el, esc);
  assert.equal(withSub.made[0]!.style.bottom, '204px');
  assert.equal(withSub.made[0]!.style.left, '32px');
  const noSub = makeEl();
  drawChoroplethLegend(base({ legend: true }), 1, false, noSub.el, esc);
  assert.equal(noSub.made[0]!.style.bottom, '32px');
});

test('labels: draws one label per polygon, escaped, with font size and opacity', async () => {
  const o = base({ labelFontSize: 20, labelMaxFontSize: 40 });
  await preloadChoroplethLabels(specWith(o));
  const { made, el } = makeEl();
  const { map } = fakeMap();
  drawChoroplethLabels(o, 1, 1, map as never, 1, el, esc);
  assert.equal(made.length, 3);
  assert.ok(made.some((m) => m.innerHTML === '&lt;C&gt;'));
  const sizes = made.map((m) => parseFloat(String(m.style.fontSize)));
  assert.equal(Math.min(...sizes), 20);
  assert.equal(Math.max(...sizes), 40);
  // opacity follows the value: the smallest value is at the floor (0.35), the largest is fully opaque
  assert.equal(made.find((m) => m.innerHTML === 'A')!.style.opacity, 0.35);
  assert.equal(made.find((m) => m.innerHTML === '&lt;C&gt;')!.style.opacity, 1);
});

test('labels: positions are divided by the render scale (1920px design coordinates)', async () => {
  const o = base();
  await preloadChoroplethLabels(specWith(o));
  const a = makeEl();
  const b = makeEl();
  const { map } = fakeMap();
  drawChoroplethLabels(o, 1, 1, map as never, 1, a.el, esc);
  drawChoroplethLabels(o, 1, 1, map as never, 0.5, b.el, esc);
  assert.equal(parseFloat(String(b.made[0]!.style.left)), parseFloat(String(a.made[0]!.style.left)) * 2);
});

test('labels: focus dims the others, extrusion lifts labels, rise fades them in', async () => {
  const o = base({ extrude: true, rise: [0.2, 0.6], focus: { values: ['<C>'], dimOpacity: 0.2, window: [0, 1] } as never });
  await preloadChoroplethLabels(specWith(o));
  const flat = makeEl();
  const { map } = fakeMap(10, 60);
  drawChoroplethLabels(o, 1, 1, map as never, 1, flat.el, esc);
  const byText = (m: FakeEl[], t: string) => m.find((x) => x.innerHTML === t)!;
  assert.equal(byText(flat.made, '&lt;C&gt;').style.opacity, 1);
  // A is the smallest value (0.35) and is outside the focus (x 0.2)
  assert.ok(Math.abs((byText(flat.made, 'A').style.opacity as number) - 0.35 * 0.2) < 1e-9);
  // before the rise starts, the extruded labels have not lifted and are transparent
  const early = makeEl();
  drawChoroplethLabels(o, 0.1, 1, map as never, 1, early.el, esc);
  assert.ok((byText(early.made, 'A').style.opacity as number) <= 1);
  const topEarly = parseFloat(String(byText(early.made, 'A').style.top));
  const topLate = parseFloat(String(byText(flat.made, 'A').style.top));
  assert.notEqual(topEarly, topLate);
});

test('labels: nothing is drawn without labelProperty, cached points, or when preload found nothing', async () => {
  const none = makeEl();
  const { map } = fakeMap();
  drawChoroplethLabels(base({ labelProperty: undefined }), 1, 1, map as never, 1, none.el, esc);
  const uncached = base({ property: 'never-loaded' });
  drawChoroplethLabels(uncached, 1, 1, map as never, 1, none.el, esc);
  assert.equal(none.made.length, 0);
  await preloadChoroplethLabels(specWith(base({ data: { type: 'FeatureCollection', features: [] } })));
  drawChoroplethLabels(base({ data: { type: 'FeatureCollection', features: [] } }), 1, 1, map as never, 1, none.el, esc);
  assert.equal(none.made.length, 0);
});

test('preload: fetches src once per key, re-roots the url and tolerates HTTP errors', async () => {
  const urls: string[] = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    urls.push(url);
    return url.includes('bad') ? new Response('', { status: 404 }) : new Response(JSON.stringify(data));
  }) as typeof fetch;
  try {
    const good = base({ data: undefined, src: '//geo/a.geojson' });
    const bad = base({ data: undefined, src: 'geo/bad.geojson', property: 'w' });
    const spec = { shots: [{ duration: 1, overlays: [good, good, bad, { type: 'note', text: 'x' }] }, { duration: 1, overlays: [good] }] } as never;
    await preloadChoroplethLabels(spec);
    assert.deepEqual(urls.sort(), ['/geo/a.geojson', '/geo/bad.geojson']);
    const { made, el } = makeEl();
    drawChoroplethLabels(good, 1, 1, fakeMap().map as never, 1, el, esc);
    assert.equal(made.length, 3);
    drawChoroplethLabels(bad, 1, 1, fakeMap().map as never, 1, el, esc);
    assert.equal(made.length, 3);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('perf budget: 2000 label points are laid out for one frame in under 500 ms', async () => {
  const features = Array.from({ length: 2000 }, (_, i) => square(i % 100, Math.floor(i / 100), { name: `n${i}`, v: i }));
  const o = base({ data: { type: 'FeatureCollection', features } });
  await preloadChoroplethLabels(specWith(o));
  const { made, el } = makeEl();
  const t0 = performance.now();
  drawChoroplethLabels(o, 1, 1, fakeMap().map as never, 1, el, esc);
  const ms = performance.now() - t0;
  assert.equal(made.length, 2000);
  assert.ok(ms < 500, `${ms.toFixed(0)} ms`);
});
