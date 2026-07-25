import { config } from '../config.js';
import { AppError } from '../errors.js';
import { validateStoryRequest, validateStoryResponse } from '../contracts/validation.js';
import type { StoryEngineRequest, StoryScript } from '../contracts/types.js';

export interface StoryEngineClient { buildScript(request: StoryEngineRequest): Promise<StoryScript>; }

const waitWithMockBehavior = async () => {
  const span = config.MOCK_MAX_DELAY_MS - config.MOCK_MIN_DELAY_MS;
  await new Promise((resolve) => setTimeout(resolve, config.MOCK_MIN_DELAY_MS + Math.round(Math.random() * span)));
  if (Math.random() < config.MOCK_ERROR_RATE) throw new AppError(503, 'The Story Engine is briefly unavailable. Please retry.', 'STORY_ENGINE_UNAVAILABLE');
};

const hash = (input: string) => [...input].reduce((value, char) => ((value << 5) - value + char.charCodeAt(0)) | 0, 0) >>> 0;
const sentences = (input: string) => input.replace(/\s+/g, ' ').match(/[^.!?]+[.!?]+|[^.!?]+$/g)?.map((sentence) => sentence.trim()).filter(Boolean) ?? [];

export class MockStoryEngineClient implements StoryEngineClient {
  async buildScript(request: StoryEngineRequest): Promise<StoryScript> {
    validateStoryRequest(request);
    await waitWithMockBehavior();
    const seed = hash(`${request.title}|${request.genre}|${request.briefStory}`);
    const source = sentences(request.briefStory);
    const sceneTotal = 3 + (seed % 2);
    const names = request.genre.toLowerCase().includes('dream') || request.genre.toLowerCase().includes('fantasy') ? ['Luna', 'Orion', 'The Whisper'] : ['Maya', 'Elias', 'Narrator'];
    const moods = ['curious', 'determined', 'vulnerable', 'triumphant'];
    const music = request.genre.toLowerCase().includes('horror') || request.genre.toLowerCase().includes('thriller') ? 'midnight_pulse' : request.genre.toLowerCase().includes('dream') ? 'glass_horizon' : 'cinematic_current';
    const scenes: StoryScript['scenes'] = Array.from({ length: sceneTotal }, (_, index) => {
      const first = source[(index * 2) % Math.max(source.length, 1)] ?? `The story opens on a turning point that changes everything.`;
      const second = source[(index * 2 + 1) % Math.max(source.length, 1)] ?? `A small choice sends the characters toward an uncertain horizon.`;
      const sceneNo = String(index + 1);
      return {
        scene_id: sceneNo,
        title: ['An Unquiet Beginning', 'The Door Opens', 'A Choice in the Dark', 'The Light Returns'][index],
        description: `${first} ${second}`,
        ambience: [{ sound: index === 0 ? 'roomtone_city_rain' : index === sceneTotal - 1 ? 'dawn_wind' : 'soft_atmosphere', volume: 0.36, loop: true, interval: 0 }],
        background_music: { track: music, volume: 0.22 + index * 0.02, fade_in_ms: 800, fade_out_ms: 1100 },
        dialogue: [
          {
            id: `${sceneNo}.1`, sentence: first, character: { name: 'Narrator', voice: 'en-US-Wavenet-D' },
            metadata: { emotion: moods[index], tone: 'cinematic', pace: 0.96, pitch: 0, volume: 1, pause_before_ms: 0, pause_after_ms: 420, emphasis: 'medium', reverb: 'light' },
            background_sounds: [{ sound: index === 0 ? 'distant_thunder' : 'soft_transition', start_offset_ms: 120, duration_ms: 800, volume: 0.23 }]
          },
          {
            id: `${sceneNo}.2`, sentence: index === sceneTotal - 1 ? 'Then the world held its breath, waiting for what they would do next.' : second,
            character: { name: names[index % names.length], voice: index % 2 ? 'en-US-Wavenet-F' : 'en-US-Wavenet-C' },
            metadata: { emotion: moods[(index + 1) % moods.length], tone: 'intimate', pace: 1.02, pitch: 0, volume: 1, pause_before_ms: 180, pause_after_ms: 650, emphasis: 'high', reverb: 'none' },
            background_sounds: [{ sound: index % 2 ? 'fabric_shift' : 'footstep_soft', start_offset_ms: 40, duration_ms: 300, volume: 0.28 }]
          }
        ]
      };
    });
    const response: StoryScript = {
      story_id: `AUD-${(seed % 90000 + 10000).toString()}`, title: request.title, genre: request.genre, language: 'English',
      global_settings: { master_volume: 0.8, default_voice: 'en-US-Wavenet-D', background_music_volume: 0.3, sfx_volume: 0.4, speech_volume: 0.9, output_format: 'mp3', sample_rate: 44100 },
      scenes
    };
    validateStoryResponse(response);
    return response;
  }
}

export class LiveStoryEngineClient implements StoryEngineClient {
  constructor(private readonly url: string) {}
  async buildScript(request: StoryEngineRequest): Promise<StoryScript> {
    validateStoryRequest(request);
    let response: Response;
    try { response = await fetch(this.url, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(request), signal: AbortSignal.timeout(60_000) }); }
    catch { throw new AppError(503, 'Could not reach the Story Engine.', 'STORY_ENGINE_UNREACHABLE'); }
    if (!response.ok) throw new AppError(502, `Story Engine rejected the request (${response.status}).`, 'STORY_ENGINE_FAILURE');
    const body: unknown = await response.json();
    try { validateStoryResponse(body); } catch { throw new AppError(502, 'Story Engine returned an invalid contract response.', 'STORY_ENGINE_CONTRACT_ERROR'); }
    return body as StoryScript;
  }
}

export const createStoryEngineClient = (): StoryEngineClient => config.STORY_ENGINE_MODE === 'live'
  ? new LiveStoryEngineClient(config.STORY_ENGINE_URL!) : new MockStoryEngineClient();
