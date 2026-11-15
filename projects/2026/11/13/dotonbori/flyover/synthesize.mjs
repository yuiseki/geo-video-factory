import fs from 'node:fs';
import { prepareNarration } from './voice.mjs';

const spec = JSON.parse(fs.readFileSync('shots/dotonbori.json', 'utf8'));
const result = await prepareNarration(spec, 'out/final');
fs.writeFileSync('out/final/prepared-shots.json', JSON.stringify(spec, null, 2));
console.log(`duration: ${spec.shots.reduce((sum, shot) => sum + shot.duration, 0).toFixed(1)} s`);
console.log(`audio: ${result.wav}`);
