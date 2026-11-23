import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { parseWav, prepareNarration, writeWav } from '../src/voice.js';
import type { ShotSpec } from '../src/types.js';

const tmpdir = () => fs.mkdtempSync(path.join(os.tmpdir(), 'gvf-synth-'));
const RATE = 24000;
const tone = (seconds: number, amp = 8000) =>
  Int16Array.from({ length: Math.round(seconds * RATE) }, (_, i) => Math.round(amp * Math.sin((i / RATE) * 2 * Math.PI * 440)));

function wavFile(dir: string, name: string, samples: Int16Array, rate = RATE): string {
  const f = path.join(dir, name);
  writeWav(f, samples, rate);
  return f;
}

function script(dir: string, name: string, body: string): string {
  const f = path.join(dir, name);
  fs.writeFileSync(f, `#!/bin/sh\n${body}\n`, { mode: 0o755 });
  return f;
}

test('writeWav and parseWav round-trip samples and rate', () => {
  const dir = tmpdir();
  const samples = Int16Array.from([0, 1, -1, 32767, -32768]);
  const f = wavFile(dir, 'a.wav', samples, 16000);
  const parsed = parseWav(fs.readFileSync(f));
  assert.equal(parsed.rate, 16000);
  assert.deepEqual([...parsed.samples], [...samples]);
  assert.ok(Math.abs(parsed.seconds - 5 / 16000) < 1e-9);
});

test('VOICEVOX: queries, synthesises, caches by parameters and mixes the clip into narration.wav', async () => {
  const dir = tmpdir();
  const body = fs.readFileSync(wavFile(dir, 'clip.wav', tone(1)));
  const calls: string[] = [];
  const bodies: Record<string, unknown>[] = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    calls.push(String(url));
    if (String(url).includes('/audio_query')) return new Response(JSON.stringify({ accent_phrases: [] }));
    bodies.push(JSON.parse(String(init!.body)));
    return new Response(body);
  }) as typeof fetch;
  try {
    const mk = (): ShotSpec => ({
      voices: { a: { speaker: 3, name: 'ずんだもん', speed: 1.1 } },
      tts: { url: 'http://tts.test', padStart: 0, padEnd: 0, pause: 0 },
      shots: [{ lines: [{ text: 'こんにちは' }] }],
    });
    const out = path.join(dir, 'out');
    fs.mkdirSync(out);
    const first = await prepareNarration(mk(), out);
    assert.equal(calls.length, 2);
    assert.ok(calls[0]!.startsWith('http://tts.test/audio_query?speaker=3&text=' + encodeURIComponent('こんにちは')));
    assert.equal(calls[1], 'http://tts.test/synthesis?speaker=3');
    assert.equal(bodies[0]!.speedScale, 1.1);
    assert.equal(bodies[0]!.prePhonemeLength, 0.05);
    const wav = parseWav(fs.readFileSync(first.wav!));
    assert.equal(wav.rate, RATE);
    assert.ok(Math.abs(wav.seconds - 1) < 0.01);
    assert.ok(wav.samples.some((s) => Math.abs(s) > 1000));
    // the same text and parameters hit the cache: no more requests
    await prepareNarration(mk(), out);
    assert.equal(calls.length, 2);
    // a changed parameter is a different clip
    const changed = mk();
    changed.voices!.a!.speed = 1.3;
    await prepareNarration(changed, out);
    assert.equal(calls.length, 4);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('VOICEVOX: engine errors name the step and the endpoint', async () => {
  const dir = tmpdir();
  const realFetch = globalThis.fetch;
  const spec = (): ShotSpec => ({ voices: { a: { speaker: 1 } }, tts: { url: 'http://tts.test' }, shots: [{ lines: [{ text: 'x' }] }] });
  try {
    globalThis.fetch = (async () => new Response('', { status: 500 })) as typeof fetch;
    await assert.rejects(prepareNarration(spec(), dir), /audio_query failed \(500\).*http:\/\/tts\.test/);
    globalThis.fetch = (async (url: string) =>
      String(url).includes('audio_query') ? new Response('{}') : new Response('', { status: 503 })) as typeof fetch;
    await assert.rejects(prepareNarration(spec(), dir), /synthesis failed \(503\)/);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('clips from several lines are placed in order, summed and clamped to 16 bit', async () => {
  const dir = tmpdir();
  const loud = fs.readFileSync(wavFile(dir, 'loud.wav', new Int16Array(RATE).fill(30000)));
  const realFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => (String(url).includes('audio_query') ? new Response('{}') : new Response(loud))) as typeof fetch;
  try {
    const spec: ShotSpec = {
      voices: { a: { speaker: 1 } },
      tts: { padStart: 0, pause: -0.5, padEnd: 0 },
      shots: [{ lines: [{ text: 'a' }, { text: 'b' }] }],
    };
    const { wav } = await prepareNarration(spec, dir);
    const p = parseWav(fs.readFileSync(wav!));
    assert.equal(Math.max(...p.samples), 32767);
    assert.equal(p.samples.every((s) => s >= -32768 && s <= 32767), true);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('Open JTalk: runs the configured binary with the text on stdin and reads its wav', async () => {
  const dir = tmpdir();
  const clip = wavFile(dir, 'clip.wav', tone(0.5));
  const dic = path.join(dir, 'dic');
  const voice = path.join(dir, 'm.htsvoice');
  fs.mkdirSync(dic);
  fs.writeFileSync(voice, '');
  const argsLog = path.join(dir, 'args.txt');
  const bin = script(dir, 'ojt.sh', `echo "$@" > "${argsLog}"\ncat > "${dir}/stdin.txt"\nfor last; do :; done\ncp "${clip}" "$last"`);
  const spec: ShotSpec = {
    tts: { engine: 'openjtalk', openjtalk: { bin, dic, voice } },
    voices: { a: { speed: 1.2, halfTone: 2 } },
    shots: [{ lines: [{ text: 'テスト' }] }],
  };
  const out = path.join(dir, 'out');
  fs.mkdirSync(out);
  const { wav } = await prepareNarration(spec, out);
  assert.ok(fs.existsSync(wav!));
  assert.equal(fs.readFileSync(path.join(dir, 'stdin.txt'), 'utf8'), 'テスト');
  const args = fs.readFileSync(argsLog, 'utf8');
  assert.ok(args.includes(`-x ${dic} -m ${voice} -r 1.2 -fm 2 -ow`));
});

test('Open JTalk: missing dictionary, missing voice and a failing binary are reported', async () => {
  const dir = tmpdir();
  const dic = path.join(dir, 'dic');
  fs.mkdirSync(dic);
  const spec = (openjtalk: object): ShotSpec => ({
    tts: { engine: 'openjtalk', openjtalk } as never,
    voices: { a: {} },
    shots: [{ lines: [{ text: 'x' }] }],
  });
  const saved = { dic: process.env.OPENJTALK_DIC, voice: process.env.OPENJTALK_VOICE };
  delete process.env.OPENJTALK_DIC;
  delete process.env.OPENJTALK_VOICE;
  try {
    await assert.rejects(prepareNarration(spec({ bin: 'true', dic: path.join(dir, 'nope') }), dir), /Open JTalk dictionary not found|Open JTalk voice model not found/);
    await assert.rejects(prepareNarration(spec({ bin: 'true', dic, voice: path.join(dir, 'nope') }), dir), /voice model not found/);
    const voice = path.join(dir, 'v.htsvoice');
    fs.writeFileSync(voice, '');
    const bin = script(dir, 'fail.sh', 'echo boom >&2\nexit 3');
    await assert.rejects(prepareNarration(spec({ bin, dic, voice }), dir), /synthesis failed \(3\): boom/);
  } finally {
    if (saved.dic !== undefined) process.env.OPENJTALK_DIC = saved.dic;
    if (saved.voice !== undefined) process.env.OPENJTALK_VOICE = saved.voice;
  }
});

test('AquesTalk: runs the configured python with the script and options, and reports failures', async () => {
  const dir = tmpdir();
  const clip = wavFile(dir, 'clip.wav', tone(0.5));
  const argsLog = path.join(dir, 'args.txt');
  const python = script(
    dir,
    'py.sh',
    `echo "$@" > "${argsLog}"\nwhile [ $# -gt 0 ]; do if [ "$1" = "--out" ]; then cp "${clip}" "$2"; fi; shift; done`,
  );
  const spec: ShotSpec = {
    tts: { engine: 'aquestalk', aquestalk: { python, appDir: '/app' } as never },
    voices: { a: { voice: 'f2', speed: 1.5 } },
    shots: [{ lines: [{ text: 'ゆっくり' }] }],
  };
  const out = path.join(dir, 'out');
  fs.mkdirSync(out);
  await prepareNarration(spec, out);
  const args = fs.readFileSync(argsLog, 'utf8');
  assert.ok(args.includes('aquestalk_tts.py --voice f2 --speed 1.5 --out'));
  assert.ok(args.includes('--text ゆっくり --app /app'));

  const bad = script(dir, 'bad.sh', 'echo nope >&2\nexit 2');
  const spec2: ShotSpec = { ...spec, tts: { engine: 'aquestalk', aquestalk: { python: bad } as never } };
  await assert.rejects(prepareNarration(spec2, dir), /AquesTalk synthesis failed \(2\): nope/);
});

test('reaction envelopes come from the synthesised samples', async () => {
  const dir = tmpdir();
  for (const f of ['a/normal_o_o.png']) {
    fs.mkdirSync(path.join(dir, path.dirname(f)), { recursive: true });
    fs.writeFileSync(path.join(dir, f), '');
  }
  const body = fs.readFileSync(wavFile(dir, 'clip.wav', tone(1)));
  const realFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => (String(url).includes('audio_query') ? new Response('{}') : new Response(body))) as typeof fetch;
  try {
    const spec: ShotSpec = {
      fps: 10,
      voices: { a: { speaker: 1 } },
      reaction: { characters: { a: { sprites: 'a' } } },
      shots: [{ lines: [{ text: 'a' }] }],
    };
    await prepareNarration(spec, dir, { projectDir: dir });
    const reaction = spec.shots[0]!.overlays!.find((o) => o.type === 'reaction') as { segs: { env: number[] }[] };
    assert.ok(reaction.segs[0]!.env.length >= 9);
    assert.equal(Math.max(...reaction.segs[0]!.env), 1);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('perf budget: mixing 120 clips of 2 s takes well under 3 s', async () => {
  const dir = tmpdir();
  const clip = fs.readFileSync(wavFile(dir, 'clip.wav', tone(2)));
  const realFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => (String(url).includes('audio_query') ? new Response('{}') : new Response(clip))) as typeof fetch;
  try {
    const spec: ShotSpec = {
      voices: { a: { speaker: 1 } },
      shots: Array.from({ length: 120 }, () => ({ lines: [{ text: 'same' }] })),
    };
    const t0 = performance.now();
    await prepareNarration(spec, dir);
    const ms = performance.now() - t0;
    assert.ok(ms < 3000, `${ms.toFixed(0)} ms`);
  } finally {
    globalThis.fetch = realFetch;
  }
});
