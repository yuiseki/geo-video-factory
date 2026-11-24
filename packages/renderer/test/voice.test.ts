import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildAquesTalkArgs, buildOpenJTalkArgs, parseWav, prepareNarration } from '../src/voice.js';
import type { ShotSpec } from '../src/types.js';

test('parseWav rejects invalid, incomplete, stereo and non-16-bit input', () => {
  assert.throws(() => parseWav(Buffer.from('nope')), /not a WAV/);
  const empty = Buffer.alloc(12);
  empty.write('RIFF', 0); empty.write('WAVE', 8);
  assert.throws(() => parseWav(empty), /without fmt or data/);

  const wav = Buffer.alloc(46);
  wav.write('RIFF', 0); wav.writeUInt32LE(38, 4); wav.write('WAVE', 8);
  wav.write('fmt ', 12); wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(2, 22); wav.writeUInt32LE(24000, 24); wav.writeUInt16LE(16, 34);
  wav.write('data', 36); wav.writeUInt32LE(2, 40);
  assert.throws(() => parseWav(wav), /16-bit mono/);
  wav.writeUInt16LE(1, 22); wav.writeUInt16LE(8, 34);
  assert.throws(() => parseWav(wav), /16-bit mono/);
});

test('prepareNarration in draft mode lays out subtitles, reactions and credits deterministically', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gvf-voice-'));
  for (const file of ['a/smile_o_o.png', 'a/surprise_o_o.png', 'b/normal_o_o.png']) {
    fs.mkdirSync(path.dirname(path.join(tmp, file)), { recursive: true });
    fs.writeFileSync(path.join(tmp, file), 'sprite');
  }
  const spec: ShotSpec = {
    voices: {
      a: { speaker: 3, name: 'ずんだもん', color: '#abc' },
      b: { speaker: 2, name: '四国めたん' },
    },
    tts: { padStart: 0.2, pause: 0.1, padEnd: 0.3, draftCps: 5 },
    reaction: { characters: { a: { sprites: 'a' }, b: { sprites: 'b' } } },
    shots: [{ duration: 1, lines: [
      { voice: 'a', text: 'こんにちは', face: 'smile', react: 'normal' },
      { voice: 'b', text: 'こんばんは', face: 'normal', react: 'surprise' },
    ] }],
  };
  const result = await prepareNarration(spec, tmp, { noVoice: true, projectDir: tmp });
  assert.equal(result.wav, null);
  assert.deepEqual(result.credits, ['音声：VOICEVOX:ずんだもん', '音声：VOICEVOX:四国めたん']);
  assert.equal(spec.shots[0]!.duration, 2.6);
  const overlays = spec.shots[0]!.overlays!;
  assert.equal(overlays.filter((o) => o.type === 'subtitle').length, 2);
  assert.equal(overlays.filter((o) => o.type === 'reaction').length, 1);
  assert.equal(fs.readFileSync(path.join(tmp, 'credits.txt'), 'utf8'), result.credits.join('\n') + '\n');
  fs.rmSync(tmp, { recursive: true, force: true });
});

test('prepareNarration validates voices and respects subtitle switches', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gvf-voice-'));
  await assert.rejects(
    prepareNarration({ shots: [{ lines: [{ text: '声がない' }] }] }, tmp, { noVoice: true }),
    /no voices defined/,
  );
  await assert.rejects(
    prepareNarration({ voices: { a: { speaker: 1 } }, shots: [{ lines: [{ voice: 'b', text: '不明' }] }] }, tmp, { noVoice: true }),
    /unknown voice/,
  );
  const spec: ShotSpec = {
    subtitles: false,
    voices: { a: { speaker: 1, name: 'a' } },
    shots: [{ lines: [{ voice: 'a', text: '字幕なし' }] }],
  };
  await prepareNarration(spec, tmp, { noVoice: true });
  assert.equal(spec.shots[0]!.overlays!.some((o) => o.type === 'subtitle'), false);
  fs.rmSync(tmp, { recursive: true, force: true });
});

test('buildOpenJTalkArgs formats CLI flags and prepareNarration emits Open JTalk credits', async () => {
  assert.deepEqual(
    buildOpenJTalkArgs({ dic: '/dic', voice: '/voice.htsvoice', speed: 1.15, halfTone: -2.5, outFile: '/tmp/out.wav' }),
    ['-x', '/dic', '-m', '/voice.htsvoice', '-r', '1.15', '-fm', '-2.5', '-ow', '/tmp/out.wav'],
  );

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'flyover-ojt-'));
  const spec: ShotSpec = {
    tts: { engine: 'openjtalk' },
    voices: {
      a: { name: '霊夢', speed: 1.2, halfTone: 1.5 },
      b: { name: '魔理沙', speed: 1.1, halfTone: -3.0 },
    },
    shots: [
      {
        lines: [
          { voice: 'a', text: '霊夢のセリフよ。' },
          { voice: 'b', text: '魔理沙のセリフだぜ。' },
        ],
      },
    ],
  };
  const { credits } = await prepareNarration(spec, tmp, { noVoice: true });
  assert.deepEqual(credits, ['音声：Open JTalk / HTS Voice "Mei"']);
  fs.rmSync(tmp, { recursive: true, force: true });
});

test('buildAquesTalkArgs formats CLI flags and prepareNarration emits AquesTalk credits', async () => {
  assert.deepEqual(
    buildAquesTalkArgs({
      script: '/repo/packages/pipeline/narration/aquestalk_tts.py',
      voiceId: 'f1',
      speed: 1.1,
      outFile: '/tmp/out.wav',
      text: 'テスト',
      appDir: '/Applications/AquesTalkPlayer.app',
    }),
    [
      '/repo/packages/pipeline/narration/aquestalk_tts.py',
      '--voice', 'f1',
      '--speed', '1.1',
      '--out', '/tmp/out.wav',
      '--text', 'テスト',
      '--app', '/Applications/AquesTalkPlayer.app',
    ],
  );

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'flyover-aq-'));
  const spec: ShotSpec = {
    tts: { engine: 'aquestalk' },
    voices: {
      a: { name: '霊夢', voice: 'f1', speed: 1.05 },
      b: { name: '魔理沙', voice: 'f2', speed: 1.0 },
    },
    shots: [
      {
        lines: [
          { voice: 'a', text: 'ゆっくりしていってね。' },
          { voice: 'b', text: '今日は地図を見ていくぜ。' },
        ],
      },
    ],
  };
  const { credits } = await prepareNarration(spec, tmp, { noVoice: true });
  assert.deepEqual(credits, ['音声：AquesTalk (ゆっくりボイス)']);
  fs.rmSync(tmp, { recursive: true, force: true });
});
