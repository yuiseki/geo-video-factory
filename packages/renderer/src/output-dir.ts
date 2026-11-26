import fs from 'node:fs';
import path from 'node:path';

/**
 * The frames directory of an output, emptied first: rendering again into the same --out replaces the previous
 * render instead of mixing old frames into the new video. Versions belong to git (commits and tags of the shot
 * JSON), not to output directories, so an output is a disposable place that the same commit fills the same way.
 * Only frames/ is cleared; files beside it (the voice cache, notes) are kept.
 */
export function freshFrames(out: string): string {
  const frames = path.join(out, 'frames');
  fs.rmSync(frames, { recursive: true, force: true });
  fs.mkdirSync(frames, { recursive: true });
  return frames;
}
