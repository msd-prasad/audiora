/* Generates original tonal fixtures for local development; no third-party recordings are embedded. */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
// lamejs publishes a browser-oriented bundle; loading that bundle directly avoids
// a Node 24 incompatibility in its package entry point.
const lameBundle = path.join(__dirname, '..', '..', 'node_modules', '.pnpm', 'lamejs@1.2.1', 'node_modules', 'lamejs', 'lame.all.js');
const lamejs = vm.runInThisContext(`${fs.readFileSync(lameBundle, 'utf8')}\nlamejs`);
const out = path.join(__dirname, '..', 'mocks', 'assets', 'audio');
fs.mkdirSync(out, { recursive: true });

const tracks = [
  ['aurora-echoes.mp3', 18, [220, 329.63, 440]],
  ['city-after-rain.mp3', 22, [164.81, 246.94, 369.99]],
  ['velvet-cosmos.mp3', 20, [196, 293.66, 493.88]],
  ['embers-at-dawn.mp3', 24, [146.83, 220, 293.66]]
];
const sr = 44100;
function render(filename, seconds, notes) {
  const encoder = new lamejs.Mp3Encoder(2, sr, 128);
  const total = seconds * sr;
  const chunk = 1152;
  const parts = [];
  for (let start = 0; start < total; start += chunk) {
    const size = Math.min(chunk, total - start);
    const left = new Int16Array(size); const right = new Int16Array(size);
    for (let i = 0; i < size; i++) {
      const t = (start + i) / sr;
      const fade = Math.min(1, t / 1.2, (seconds - t) / 1.4);
      const pad = notes.reduce((sum, note, index) => sum + Math.sin(Math.PI * 2 * note * t + index) * (0.10 / (index + 1)), 0);
      const shimmer = Math.sin(Math.PI * 2 * (notes[0] * 2.01) * t) * 0.025;
      const pulse = Math.sin(Math.PI * 2 * 0.18 * t) * 0.02;
      const sample = Math.max(-0.78, Math.min(0.78, (pad + shimmer + pulse) * fade));
      left[i] = sample * 32767; right[i] = (sample * 0.94 + Math.sin(Math.PI * 2 * 0.11 * t) * 0.012) * 32767;
    }
    const encoded = encoder.encodeBuffer(left, right); if (encoded.length) parts.push(Buffer.from(encoded));
  }
  const end = encoder.flush(); if (end.length) parts.push(Buffer.from(end));
  fs.writeFileSync(path.join(out, filename), Buffer.concat(parts));
}
tracks.forEach((track) => render(...track));
