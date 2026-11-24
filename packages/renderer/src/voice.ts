// Narration: synthesize each shot's lines with VOICEVOX, stretch shots to fit, add subtitles,
// and write one narration WAV for the whole timeline. Used by render.ts before drawing.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { layoutLines, wrapSubtitle, estimateSeconds, levelEnvelope } from './lib.js';
import type { ReactionSegment, ShotSpec, TtsConfig, VoiceConfig } from './types.js';

// Speaker colors for subtitles when a voice does not set one (yellow, then light red, ...).
const COLORS = ['#ffe94a', '#ff8f8f', '#8fd3ff', '#b8f28f'];

export interface ParsedWav {
  rate: number;
  samples: Int16Array;
  seconds: number;
}

export function parseWav(buf: Buffer): ParsedWav {
  if (buf.toString('ascii', 0, 4) !== 'RIFF' || buf.toString('ascii', 8, 12) !== 'WAVE') {
    throw new Error('not a WAV file');
  }
  let off = 12;
  let fmt: { channels: number; rate: number; bits: number } | undefined;
  let data: Buffer | undefined;
  while (off + 8 <= buf.length) {
    const id = buf.toString('ascii', off, off + 4);
    const size = buf.readUInt32LE(off + 4);
    if (id === 'fmt ') {
      fmt = {
        channels: buf.readUInt16LE(off + 10),
        rate: buf.readUInt32LE(off + 12),
        bits: buf.readUInt16LE(off + 22),
      };
    }
    if (id === 'data') data = buf.subarray(off + 8, off + 8 + size);
    off += 8 + size + (size % 2);
  }
  if (!fmt || !data) throw new Error('WAV without fmt or data');
  if (fmt.bits !== 16 || fmt.channels !== 1) {
    throw new Error(`expected 16-bit mono, got ${fmt.bits}-bit ${fmt.channels}ch`);
  }
  const samples = new Int16Array(data.buffer.slice(data.byteOffset, data.byteOffset + data.length));
  return { rate: fmt.rate, samples, seconds: samples.length / fmt.rate };
}

export function writeWav(file: string, samples: Int16Array, rate: number): void {
  const h = Buffer.alloc(44);
  h.write('RIFF', 0);
  h.writeUInt32LE(36 + samples.length * 2, 4);
  h.write('WAVE', 8);
  h.write('fmt ', 12);
  h.writeUInt32LE(16, 16);
  h.writeUInt16LE(1, 20);
  h.writeUInt16LE(1, 22);
  h.writeUInt32LE(rate, 24);
  h.writeUInt32LE(rate * 2, 28);
  h.writeUInt16LE(2, 32);
  h.writeUInt16LE(16, 34);
  h.write('data', 36);
  h.writeUInt32LE(samples.length * 2, 40);
  fs.writeFileSync(file, Buffer.concat([h, Buffer.from(samples.buffer, samples.byteOffset, samples.length * 2)]));
}

const DEFAULT_OPENJTALK_DICS = [
  '/opt/homebrew/opt/open-jtalk/dic',
  '/usr/local/opt/open-jtalk/dic',
  '/var/lib/mecab/dic/open-jtalk/naist-jdic',
];

const DEFAULT_OPENJTALK_VOICES = [
  '/opt/homebrew/opt/open-jtalk/voice/mei/mei_normal.htsvoice',
  '/usr/local/opt/open-jtalk/voice/mei/mei_normal.htsvoice',
  '/usr/share/hts-voice/mei/mei_normal.htsvoice',
];

export interface OpenJTalkArgsOptions {
  dic: string;
  voice: string;
  speed: number;
  halfTone: number;
  outFile: string;
}

export function buildOpenJTalkArgs({ dic, voice, speed, halfTone, outFile }: OpenJTalkArgsOptions): string[] {
  return ['-x', dic, '-m', voice, '-r', String(speed), '-fm', String(halfTone), '-ow', outFile];
}

function resolveExistingPath(explicit: string | undefined, envName: string, candidates: string[], label: string): string {
  if (explicit !== undefined) {
    if (explicit && fs.existsSync(explicit)) return explicit;
    throw new Error(`Open JTalk ${label} not found: ${explicit}`);
  }
  const fromEnv = process.env[envName]?.trim();
  for (const candidate of [fromEnv, ...candidates]) {
    if (candidate && fs.existsSync(candidate)) return candidate;
  }
  throw new Error(`Open JTalk ${label} not found (set tts.openjtalk or ${envName})`);
}

function synthOpenJTalk(tts: TtsConfig, voice: VoiceConfig, text: string, file: string): void {
  const bin = tts.openjtalk?.bin ?? process.env.OPENJTALK_BIN?.trim() ?? 'open_jtalk';
  const dic = resolveExistingPath(tts.openjtalk?.dic, 'OPENJTALK_DIC', DEFAULT_OPENJTALK_DICS, 'dictionary');
  const htsvoice = resolveExistingPath(voice.htsvoice ?? tts.openjtalk?.voice, 'OPENJTALK_VOICE', DEFAULT_OPENJTALK_VOICES, 'voice model');
  const args = buildOpenJTalkArgs({
    dic,
    voice: htsvoice,
    speed: voice.speed ?? tts.speed ?? 1.0,
    halfTone: voice.halfTone ?? 0,
    outFile: file,
  });
  const res = spawnSync(bin, args, { input: text, encoding: 'utf8' });
  if (res.status !== 0) {
    throw new Error(`Open JTalk synthesis failed (${res.status}): ${res.stderr || res.error?.message || 'unknown error'}`);
  }
}

export interface AquesTalkArgsOptions {
  script: string;
  voiceId: string;
  speed: number;
  outFile: string;
  text: string;
  appDir?: string;
}

export function buildAquesTalkArgs({ script, voiceId, speed, outFile, text, appDir }: AquesTalkArgsOptions): string[] {
  const args = [script, '--voice', voiceId, '--speed', String(speed), '--out', outFile, '--text', text];
  if (appDir) args.push('--app', appDir);
  return args;
}

function synthAquesTalk(tts: TtsConfig, voice: VoiceConfig, text: string, file: string): void {
  const python = tts.aquestalk?.python ?? process.env.PYTHON?.trim() ?? 'python3';
  const script = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..', '..', 'pipeline', 'narration', 'aquestalk_tts.py');
  const appDir = tts.aquestalk?.appDir ?? process.env.AQUESTALK_APP_DIR?.trim();
  const args = buildAquesTalkArgs({
    script,
    voiceId: voice.voice ?? 'f1',
    speed: voice.speed ?? tts.speed ?? 1.0,
    outFile: file,
    text,
    appDir,
  });
  const res = spawnSync(python, args, { encoding: 'utf8' });
  if (res.status !== 0) {
    throw new Error(`AquesTalk synthesis failed (${res.status}): ${res.stderr || res.error?.message || 'unknown error'}`);
  }
}

async function synth(tts: TtsConfig, voice: VoiceConfig, text: string, cacheDir: string): Promise<ParsedWav> {
  const engine = voice.engine ?? tts.engine ?? 'voicevox';
  const params =
    engine === 'openjtalk'
      ? {
          engine,
          text,
          speed: voice.speed ?? tts.speed ?? 1.0,
          halfTone: voice.halfTone ?? 0,
          htsvoice: voice.htsvoice ?? tts.openjtalk?.voice ?? '',
        }
      : engine === 'aquestalk'
        ? {
            engine,
            text,
            voice: voice.voice ?? 'f1',
            speed: voice.speed ?? tts.speed ?? 1.0,
          }
        : {
            engine,
            speaker: voice.speaker ?? 0,
            text,
            speed: voice.speed ?? tts.speed ?? 1.25,
            pitch: voice.pitch ?? 0,
            intonation: voice.intonation ?? 1,
            volume: voice.volume ?? 1,
          };
  const key = crypto.createHash('sha1').update(JSON.stringify(params)).digest('hex').slice(0, 16);
  const file = path.join(cacheDir, key + '.wav');
  if (!fs.existsSync(file)) {
    if (engine === 'openjtalk') {
      synthOpenJTalk(tts, voice, text, file);
    } else if (engine === 'aquestalk') {
      synthAquesTalk(tts, voice, text, file);
    } else {
      const base = tts.url ?? 'http://127.0.0.1:50021';
      const q = await fetch(`${base}/audio_query?speaker=${params.speaker}&text=${encodeURIComponent(text)}`, { method: 'POST' });
      if (!q.ok) throw new Error(`VOICEVOX audio_query failed (${q.status}). Is the engine running at ${base}?`);
      const query = (await q.json()) as Record<string, unknown>;
      Object.assign(query, {
        speedScale: params.speed,
        pitchScale: params.pitch,
        intonationScale: params.intonation,
        volumeScale: params.volume,
        prePhonemeLength: 0.05,
        postPhonemeLength: 0.05,
      });
      const s = await fetch(`${base}/synthesis?speaker=${params.speaker}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(query),
      });
      if (!s.ok) throw new Error(`VOICEVOX synthesis failed (${s.status})`);
      fs.writeFileSync(file, Buffer.from(await s.arrayBuffer()));
    }
  }
  return parseWav(fs.readFileSync(file));
}

export interface PrepareNarrationOptions {
  noVoice?: boolean;
  projectDir?: string;
}

// Mutates spec: stretches shot durations, appends subtitle overlays, adds voice credits.
// Returns { wav, credits } (wav is null when noVoice).
export async function prepareNarration(
  spec: ShotSpec,
  outDir: string,
  { noVoice = false, projectDir = process.cwd() }: PrepareNarrationOptions = {},
): Promise<{ wav: string | null; credits: string[] }> {
  const voices = spec.voices ?? {};
  const tts = spec.tts ?? {};
  const names = Object.keys(voices);
  const hasLines = spec.shots.some((s) => s.lines?.length);
  if (!hasLines) return { wav: null, credits: [] };

  const cacheDir = path.join(outDir, 'voice-cache');
  fs.mkdirSync(cacheDir, { recursive: true });
  let rate = 24000;
  const placed: { at: number; samples: Int16Array }[] = [];
  let t0 = 0;
  const used = new Set<string>();

  for (const shot of spec.shots) {
    const lines = shot.lines ?? [];
    const clips: { seconds: number; rate?: number; samples?: Int16Array }[] = [];
    for (const ln of lines) {
      const vname = ln.voice ?? names[0];
      if (!vname) throw new Error('no voices defined under "voices"');
      const voice = voices[vname];
      if (!voice) throw new Error(`unknown voice "${vname}" (define it under "voices")`);
      used.add(vname);
      if (noVoice) {
        clips.push({ seconds: estimateSeconds(ln.text, tts.draftCps ?? 6.5) });
      } else {
        const w = await synth(tts, voice, ln.speech ?? ln.text, cacheDir);
        rate = w.rate;
        clips.push(w);
      }
    }

    const lay = layoutLines(
      clips.map((c) => c.seconds),
      {
        duration: shot.duration ?? 0,
        padStart: tts.padStart ?? 0.3,
        pause: tts.pause ?? 0.25,
        padEnd: tts.padEnd ?? 0.4,
      },
    );
    shot.duration = lay.duration;
    shot.overlays = shot.overlays ?? [];

    lines.forEach((ln, i) => {
      const vname = ln.voice ?? names[0]!;
      if (spec.subtitles !== false && shot.subtitles !== false) {
        shot.overlays!.push({
          type: 'subtitle',
          text: wrapSubtitle(ln.text, tts.wrap ?? 26),
          show: lay.windows[i],
          fade: 0,
          color: voices[vname]!.color ?? COLORS[names.indexOf(vname) % COLORS.length],
        });
      }
      const clip = clips[i]!;
      if (clip.samples) placed.push({ at: t0 + lay.starts[i]!, samples: clip.samples });
    });

    // reaction wipe: one overlay per shot holding every line's speaker, faces and loudness (seconds in the shot)
    if (spec.reaction) {
      const segs: ReactionSegment[] = lines.map((ln, i) => {
        const clip = clips[i]!;
        return {
          t0: lay.starts[i]!,
          t1: i < lines.length - 1 ? lay.starts[i + 1]! : lay.duration,
          speaker: ln.voice ?? names[0]!,
          face: ln.face ?? 'normal',
          react: ln.react ?? 'normal',
          env: clip.samples ? levelEnvelope(clip.samples, clip.rate ?? rate, spec.fps ?? 30) : [],
        };
      });
      // fail now, not with a broken image mid-render: every face must have its sprites
      for (const g of segs) {
        const checks: [string, string][] = [
          [g.speaker, g.face],
          ...Object.keys(spec.reaction.characters ?? {})
            .filter((k) => k !== g.speaker)
            .map((k): [string, string] => [k, g.react]),
        ];
        for (const [who, face] of checks) {
          const dir = spec.reaction.characters?.[who]?.sprites;
          if (dir && !fs.existsSync(path.join(projectDir, dir, `${face}_o_o.png`))) {
            throw new Error(`reaction: no sprite "${face}" for ${who} (looked for ${path.join(projectDir, dir, `${face}_o_o.png`)})`);
          }
        }
      }
      shot.overlays.push({ type: 'reaction', show: [0, 1], fade: 0, segs });
    }
    t0 += shot.duration;
  }

  const credits = [
    ...new Set(
      [...used].map((v) => {
        const voice = voices[v]!;
        if (voice.credit) return voice.credit;
        const engine = voice.engine ?? tts.engine ?? 'voicevox';
        if (engine === 'openjtalk') return '音声：Open JTalk / HTS Voice "Mei"';
        if (engine === 'aquestalk') return '音声：AquesTalk (ゆっくりボイス)';
        return `音声：VOICEVOX:${voice.name ?? v}`;
      }),
    ),
  ];
  spec.credits = [...(spec.credits ?? []), ...credits];
  fs.writeFileSync(path.join(outDir, 'credits.txt'), credits.join('\n') + '\n');
  if (noVoice) return { wav: null, credits };

  const total = new Int16Array(Math.ceil(t0 * rate) + 1);
  for (const p of placed) {
    const start = Math.round(p.at * rate);
    for (let i = 0; i < p.samples.length && start + i < total.length; i++) {
      total[start + i] = Math.max(-32768, Math.min(32767, total[start + i]! + p.samples[i]!));
    }
  }
  const wav = path.join(outDir, 'narration.wav');
  writeWav(wav, total, rate);
  return { wav, credits };
}
