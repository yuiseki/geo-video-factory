import fs from 'node:fs';
import path from 'node:path';
import { registerVideoE2E } from './video-e2e.js';

const appDir = process.env.AQUESTALK_APP_DIR?.trim() || '/Applications/AquesTalkPlayer.app';
const hasAquesTalk = fs.existsSync(path.join(appDir, 'Contents/Frameworks/libAquesTalk1-f1.dylib'));

registerVideoE2E({
  name: 'narration-yukkuri',
  fixture: 'narration-yukkuri.json',
  minimumDuration: 4,
  prepareScript: 'test/e2e/prepare-character-yukkuri.py',
  generatedProject: true,
  noVoice: false,
  expectAudio: true,
  ...(hasAquesTalk ? {} : { skipReason: 'AquesTalkPlayer.app not installed' }),
});
