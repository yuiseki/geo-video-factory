import { registerVideoE2E } from './video-e2e.js';

registerVideoE2E({ name: 'base', fixture: 'base-video.json', minimumDuration: 0.5 });
registerVideoE2E({ name: 'base-supersample', fixture: 'base-video.json', minimumDuration: 0.5, supersample: 2 });
