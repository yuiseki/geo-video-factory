import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { configureOverlayRenderer, drawOverlays, setOverlayTime } from '../src/page/overlays.js';
import { FakeEl, fakeMap, installFakeDocument, type Call } from './support/fake-dom.js';
import type { Shot, ShotSpec } from '../src/types.js';

let dom: ReturnType<typeof installFakeDocument>;
beforeEach(() => { dom = installFakeDocument(); });
afterEach(() => dom.restore());

function setup(shots: Shot[], extra: Partial<ShotSpec> = {}) {
  const spec = { shots, width: 1920, height: 1080, ...extra } as ShotSpec;
  const { map, calls } = fakeMap();
  configureOverlayRenderer({ map: map as never, spec, overlayEl: dom.overlay as never, tintEl: dom.tint as never });
  return { spec, calls };
}
const last = (calls: Call[], id: string, prop: string) => [...calls].reverse().find((c) => c.id === id && c.prop === prop)?.value;
const classes = () => dom.overlay.children.map((c) => c.className);

test('map pass shows only the current shot\'s map layers (line casing, polygon fill, focus variants)', () => {
  const shots: Shot[] = [
    { duration: 2, overlays: [{ type: 'line', coords: [[0, 0], [1, 1]] }, { type: 'polygon', coords: [[0, 0], [1, 0], [1, 1], [0, 0]] }] },
    { duration: 2, overlays: [
      { type: 'choropleth', src: 'a.json', property: 'p', breaks: [1, 2], colors: ['#fff', '#000'], focus: { values: ['x'] } } as never,
      { type: 'base', layer: 'std' },
      { type: 'heatmap', data: {} },
    ] },
  ];
  const { calls } = setup(shots);
  drawOverlays(0, shots[0]!, 0.5, 'map');
  const vis = (id: string) => last(calls, id, 'visibility');
  assert.equal(vis('ov-0-0'), 'visible');
  assert.equal(vis('ov-0-0-casing'), 'visible');
  assert.equal(vis('ov-0-1-fill'), 'visible');
  for (const id of ['ov-1-0', 'ov-1-0-fill', 'ov-1-0-focus', 'ov-1-0-focus-fill', 'ov-1-1', 'ov-1-2']) assert.equal(vis(id), 'none', id);
  calls.length = 0;
  drawOverlays(1, shots[1]!, 0.5, 'map');
  assert.equal(vis('ov-0-0'), 'none');
  assert.equal(vis('ov-1-0-focus-fill'), 'visible');
  assert.equal(vis('ov-1-2'), 'visible');
});

test('line overlay draws progressively and fades through its window', () => {
  const shot: Shot = { duration: 2, overlays: [{ type: 'line', coords: [[0, 0], [10, 0]], draw: [0.2, 0.6], show: [0, 1] }] };
  const { calls } = setup([shot]);
  drawOverlays(0, shot, 0.4, 'map');
  const data = calls.find((c) => c.fn === 'setData')!.value as { geometry: { coordinates: number[][] } };
  assert.ok(Math.abs(data.geometry.coordinates.at(-1)![0]! - 5) < 1e-9);
  assert.equal(last(calls, 'ov-0-0', 'line-opacity'), 1);
  assert.equal(last(calls, 'ov-0-0-casing', 'line-opacity'), 0.9);
  calls.length = 0;
  drawOverlays(0, shot, 0.0, 'map');
  assert.deepEqual((calls.find((c) => c.fn === 'setData')!.value as { geometry: { coordinates: number[][] } }).geometry.coordinates.length >= 1, true);
});

test('overlay outside its show window is fully transparent', () => {
  const shot: Shot = { duration: 2, overlays: [{ type: 'base', layer: 'std', show: [0.5, 0.9] }, { type: 'heatmap', data: {}, show: [0.5, 0.9], opacity: 0.5 }] };
  const { calls } = setup([shot]);
  drawOverlays(0, shot, 0.1, 'map');
  assert.equal(last(calls, 'ov-0-0', 'raster-opacity'), 0);
  assert.equal(last(calls, 'ov-0-1', 'heatmap-opacity'), 0);
  drawOverlays(0, shot, 0.7, 'map');
  assert.equal(last(calls, 'ov-0-0', 'raster-opacity'), 1);
  assert.equal(last(calls, 'ov-0-1', 'heatmap-opacity'), 0.5);
});

test('polygon and choropleth opacities scale by overlay opacity and focus dimming', () => {
  const poly: Shot = { duration: 1, overlays: [{ type: 'polygon', coords: [[0, 0]], fillOpacity: 0.5 }] };
  const { calls } = setup([poly]);
  drawOverlays(0, poly, 0.5, 'map');
  assert.equal(last(calls, 'ov-0-0-fill', 'fill-opacity'), 0.5);

  const chor: Shot = { duration: 1, overlays: [{ type: 'choropleth', src: 'a', property: 'p', breaks: [1, 2], colors: ['#fff', '#000'], extrude: true, rise: [0, 0.5], opacity: 0.8, focus: { values: ['x'], window: [0, 1], dimOpacity: 0.25 } } as never] };
  const s2 = setup([chor]);
  drawOverlays(0, chor, 0.25, 'map');
  assert.equal(last(s2.calls, 'ov-0-0-focus', 'line-opacity'), 1);
  assert.equal(last(s2.calls, 'ov-0-0-focus-fill', 'fill-extrusion-opacity'), 0.8);
  assert.ok((last(s2.calls, 'ov-0-0', 'line-opacity') as number) < 1);
  assert.ok(Array.isArray(last(s2.calls, 'ov-0-0-fill', 'fill-extrusion-height')));
});

test('dom pass clears the overlay layer and redraws it from scratch each frame', () => {
  const shot: Shot = { duration: 2, overlays: [{ type: 'note', text: 'n' }] };
  setup([shot]);
  drawOverlays(0, shot, 0.5, 'dom');
  drawOverlays(0, shot, 0.6, 'dom');
  assert.deepEqual(classes(), ['o note']);
});

test('label text is HTML-escaped and positioned from the projected point', () => {
  const shot: Shot = { duration: 2, overlays: [{ type: 'label', text: '<b>&</b>', at: [10, 20], style: 'tag' }] };
  setup([shot]);
  drawOverlays(0, shot, 0.9, 'dom');
  const el = dom.overlay.children[0]!;
  assert.equal(el.className, 'o label tag');
  assert.ok(el.innerHTML.includes('&lt;b&gt;&amp;&lt;/b&gt;'));
  assert.ok(!el.innerHTML.includes('<b>'));
  assert.ok(el.style.left !== undefined && el.style.top !== undefined);
});

test('label with a leader draws an svg leader before the label', () => {
  const shot: Shot = { duration: 2, overlays: [{ type: 'label', text: 'x', at: [10, 20], offset: [100, -50], leader: true }] };
  setup([shot]);
  drawOverlays(0, shot, 0.9, 'dom');
  assert.deepEqual(classes(), ['o leader', 'o label']);
  assert.ok(dom.overlay.children[0]!.innerHTML.includes('<svg'));
});

test('dom pass skips map overlays and overlays that have not started', () => {
  const shot: Shot = { duration: 2, overlays: [{ type: 'line', coords: [[0, 0], [1, 1]] }, { type: 'note', text: 'late', show: [0.8, 1] }] };
  setup([shot]);
  drawOverlays(0, shot, 0.1, 'dom');
  assert.deepEqual(classes(), []);
});

test('subtitle moves the credit up and chapter darkens the tint', () => {
  const shot: Shot = { duration: 4, overlays: [{ type: 'subtitle', text: 'こんにちは' }, { type: 'chapter', text: '第1章', kicker: 'K' }] };
  setup([shot]);
  drawOverlays(0, shot, 0.5, 'map');
  assert.ok(Number(dom.tint.style.opacity) > 0.3);
  drawOverlays(0, shot, 0.5, 'dom');
  assert.equal(dom.credit.style.bottom, '196px');
  assert.ok(classes().includes('o subtitle'));
  assert.ok(classes().includes('o chapter'));
});

test('credit stays at the bottom edge without a subtitle and follows the reaction side', () => {
  const shot: Shot = { duration: 2, overlays: [{ type: 'note', text: 'n' }] };
  setup([shot], { reaction: { side: 'right', characters: {} } as never });
  drawOverlays(0, shot, 0.5, 'dom');
  assert.equal(dom.credit.style.bottom, '16px');
  assert.equal(dom.credit.style.left, '24px');
  setup([shot]);
  drawOverlays(0, shot, 0.5, 'dom');
  assert.equal(dom.credit.style.right, '24px');
});

test('counter, quote, note and sticker produce their own elements with escaped text', () => {
  const shot: Shot = { duration: 4, overlays: [
    { type: 'counter', value: 1234, caption: '<c>', unit: '人', roll: true } as never,
    { type: 'quote', text: 'ab', source: 's', cps: 1000 } as never,
    { type: 'note', text: 'n<' },
    { type: 'sticker', src: '/a.png', credit: 'cr' } as never,
  ] };
  setup([shot]);
  drawOverlays(0, shot, 0.9, 'dom');
  assert.deepEqual(classes(), ['o counter', 'o quote', 'o note', 'o sticker']);
  assert.ok(dom.overlay.children[0]!.innerHTML.includes('&lt;c&gt;'));
  assert.ok(dom.overlay.children[0]!.innerHTML.includes('wheel'));
  assert.ok(dom.overlay.children[2]!.innerHTML.includes('n&lt;'));
});

test('reaction draws one sprite per character and dims the listener', () => {
  const shot: Shot = { duration: 4, overlays: [{ type: 'reaction', segs: [{ t0: 0, t1: 4, speaker: 'a', face: 'happy', react: 'normal', env: [1, 1] }] } as never] };
  setup([shot], { fps: 30, reaction: { characters: { a: { sprites: '/chars/a/' }, b: { sprites: 'chars/b' } }, order: ['a', 'b'] } as never });
  setOverlayTime(1);
  drawOverlays(0, shot, 0.5, 'dom');
  const html = dom.overlay.children[0]!.innerHTML;
  assert.ok(html.includes('/chars/a/happy_'));
  assert.ok(html.includes('/chars/b/normal_'));
  assert.equal(html.split('brightness(0.72)').length - 1, 1);
});

test('panel and photo marker image paths lose leading slashes and are re-rooted', () => {
  const shot: Shot = { duration: 4, overlays: [
    { type: 'panel', src: '//img/x.jpg', credit: 'c' } as never,
    { type: 'photo_marker', src: '/img/y.jpg', at: [1, 2], cameraAt: [3, 4], bridgeAt: [5, 6] } as never,
  ] };
  setup([shot]);
  drawOverlays(0, shot, 0.9, 'dom');
  assert.ok(dom.overlay.children[0]!.innerHTML.includes('src="/img/x.jpg"'));
  assert.deepEqual(classes().slice(1), ['o photo-connector', 'o photo-marker-card']);
  assert.ok(dom.overlay.children[2]!.innerHTML.includes('src="/img/y.jpg"'));
});

test('chart overlay renders an svg path with one point per datum', () => {
  const shot: Shot = { duration: 6, overlays: [{ type: 'chart', points: [['2020-01', 1], ['2020-02', 4], ['2020-03', 9]], labels: [2], yticks: [0, 5], xlabels: [['a', 0]] } as never] };
  setup([shot]);
  drawOverlays(0, shot, 0.95, 'dom');
  const html = dom.overlay.children[0]!.innerHTML;
  assert.ok(html.includes('class="line"'));
  assert.equal(html.split('class="pt"').length - 1, 3);
  assert.ok(html.includes('class="pulse"'));
});

test('perf budget: drawing 300 labels for one frame stays under 500 ms', () => {
  const overlays = Array.from({ length: 300 }, (_, i) => ({ type: 'label' as const, text: `L${i}`, at: [i % 50, i % 30] as [number, number] }));
  const shot: Shot = { duration: 2, overlays };
  setup([shot]);
  const t0 = performance.now();
  drawOverlays(0, shot, 0.9, 'dom');
  const ms = performance.now() - t0;
  assert.equal(dom.overlay.children.length, 300);
  assert.ok(ms < 500, `${ms.toFixed(0)} ms`);
});

test('FakeEl clears children when textContent is reset', () => {
  const e = new FakeEl();
  e.appendChild(new FakeEl());
  e.textContent = '';
  assert.equal(e.children.length, 0);
});
