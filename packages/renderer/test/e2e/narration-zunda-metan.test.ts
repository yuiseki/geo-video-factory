import { spawnSync } from 'node:child_process';
import { registerVideoE2E } from './video-e2e.js';

const hasVoicevox =
  spawnSync('curl', ['-fsS', '--max-time', '1', 'http://127.0.0.1:50021/version']).status === 0;

registerVideoE2E({
  name: 'narration-zunda-metan',
  fixture: 'narration-zunda-metan.json',
  minimumDuration: 4,
  prepareScript: 'test/e2e/prepare-character-zunda-metan.py',
  generatedProject: true,
  noVoice: false,
  expectAudio: true,
  ...(hasVoicevox ? {} : { skipReason: 'VOICEVOX engine not running at 127.0.0.1:50021' }),
});
