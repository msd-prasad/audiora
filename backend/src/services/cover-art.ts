import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export interface MockAsset { audioFile: string; coverFile: string; fallbackDurationSeconds: number; }
// The fallback only protects a partially copied fixture folder. Normal mock responses
// parse the actual MPEG frames so scene markers match the audio a listener receives.
const assets: MockAsset[] = [
  { audioFile: 'aurora-echoes.mp3', coverFile: 'aurora-echoes.svg', fallbackDurationSeconds: 18 },
  { audioFile: 'city-after-rain.mp3', coverFile: 'city-after-rain.svg', fallbackDurationSeconds: 22 },
  { audioFile: 'velvet-cosmos.mp3', coverFile: 'velvet-cosmos.svg', fallbackDurationSeconds: 20 },
  { audioFile: 'embers-at-dawn.mp3', coverFile: 'embers-at-dawn.svg', fallbackDurationSeconds: 24 }
];
const hash = (input: string) => [...input].reduce((value, char) => ((value << 5) - value + char.charCodeAt(0)) | 0, 0) >>> 0;
export const mockAssetForGenre = (genre: string, seed = '') => assets[hash(`${genre}|${seed}`) % assets.length];
export const coverArtFor = (genre: string, seed = '') => `/api/assets/covers/${mockAssetForGenre(genre, seed).coverFile}`;

const audioRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../mocks/assets/audio');
const durationCache = new Map<string, number>();
const bitrates = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320];
const sampleRates = [44100, 48000, 32000];

function durationFromMpegFrames(bytes: Buffer) {
  let index = bytes.subarray(0, 3).toString('ascii') === 'ID3' ? 10 + ((bytes[6] & 0x7f) << 21) + ((bytes[7] & 0x7f) << 14) + ((bytes[8] & 0x7f) << 7) + (bytes[9] & 0x7f) : 0;
  let frames = 0; let sampleRate = 44100;
  while (index + 4 <= bytes.length && bytes[index] === 0xff && (bytes[index + 1] & 0xe6) === 0xe2) {
    const bitrateIndex = (bytes[index + 2] >> 4) & 0x0f; const rateIndex = (bytes[index + 2] >> 2) & 0x03; const padding = (bytes[index + 2] >> 1) & 0x01;
    const bitrate = bitrates[bitrateIndex]; sampleRate = sampleRates[rateIndex];
    if (!bitrate || !sampleRate) break;
    const frameLength = Math.floor((144 * bitrate * 1000) / sampleRate) + padding;
    if (index + frameLength > bytes.length) break;
    frames++; index += frameLength;
  }
  return frames ? Number(((frames * 1152) / sampleRate).toFixed(4)) : 0;
}

export async function mockAudioDuration(asset: MockAsset) {
  const cached = durationCache.get(asset.audioFile); if (cached) return cached;
  try {
    const duration = durationFromMpegFrames(await readFile(resolve(audioRoot, asset.audioFile)));
    if (duration) { durationCache.set(asset.audioFile, duration); return duration; }
  } catch { /* mock mode stays usable if a developer has not run the fixture generator yet */ }
  return asset.fallbackDurationSeconds;
}
