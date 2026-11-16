import { registerVideoE2E } from './video-e2e.js';

registerVideoE2E({
  name: 'character-yukkuri',
  fixture: 'character-yukkuri.json',
  minimumDuration: 2,
  prepareScript: 'test/e2e/prepare-character-yukkuri.py',
  generatedProject: true,
});
