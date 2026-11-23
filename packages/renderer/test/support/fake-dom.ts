// A just-enough DOM and map for unit-testing the overlay drawing code in Node.

export class FakeEl {
  className = '';
  innerHTML = '';
  style: Record<string, unknown> = {};
  children: FakeEl[] = [];
  appendChild(c: FakeEl): FakeEl {
    this.children.push(c);
    return c;
  }
  set textContent(v: string) {
    if (v === '') this.children = [];
  }
  get textContent(): string {
    return this.innerHTML;
  }
}

export interface Call {
  fn: 'layout' | 'paint' | 'setData';
  id: string;
  prop?: string;
  value: unknown;
}

export function installFakeDocument(): { credit: FakeEl; overlay: FakeEl; tint: FakeEl; restore: () => void } {
  const credit = new FakeEl();
  const overlay = new FakeEl();
  const tint = new FakeEl();
  const g = globalThis as Record<string, unknown>;
  const prev = g.document;
  g.document = {
    createElement: () => new FakeEl(),
    getElementById: (id: string) => (id === 'credit' ? credit : id === 'overlay' ? overlay : tint),
  };
  return { credit, overlay, tint, restore: () => { g.document = prev; } };
}

export function fakeMap(zoom = 10, pitch = 0) {
  const calls: Call[] = [];
  const map = {
    once: () => {},
    triggerRepaint: () => {},
    jumpTo: () => {},
    setTerrain: () => {},
    setLayoutProperty: (id: string, prop: string, value: unknown) => calls.push({ fn: 'layout', id, prop, value }),
    setPaintProperty: (id: string, prop: string, value: unknown) => calls.push({ fn: 'paint', id, prop, value }),
    getSource: (id: string) => ({ setData: (value: unknown) => calls.push({ fn: 'setData', id, value }) }),
    project: (ll: [number, number]) => ({ x: ll[0] * 10, y: ll[1] * 10 }),
    setPadding: () => {},
    getZoom: () => zoom,
    getPitch: () => pitch,
  };
  return { map, calls };
}
