import { registerVideoE2E } from './video-e2e.js';

registerVideoE2E({
  name: 'character-zunda-metan',
  fixture: 'character-zunda-metan.json',
  minimumDuration: 4,
  prepareScript: 'test/e2e/prepare-character-zunda-metan.py',
  generatedProject: true,
});
