import { config } from '../config.js';
import { AppError } from '../errors.js';
import { validateAudioResponse, validateStoryResponse } from '../contracts/validation.js';
import type { AudioEngineResponse, StoryScript } from '../contracts/types.js';
import { mockAssetForGenre, mockAudioDuration } from '../services/cover-art.js';

export interface AudioEngineClient { renderAudio(script: StoryScript): Promise<AudioEngineResponse>; }
const pause = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export class MockAudioEngineClient implements AudioEngineClient {
  async renderAudio(script: StoryScript): Promise<AudioEngineResponse> {
    validateStoryResponse(script);
    const span = config.MOCK_MAX_DELAY_MS - config.MOCK_MIN_DELAY_MS;
    await pause(config.MOCK_MIN_DELAY_MS + Math.round(Math.random() * span));
    if (Math.random() < config.MOCK_ERROR_RATE) throw new AppError(503, 'The Audio Engine is briefly unavailable. Please retry.', 'AUDIO_ENGINE_UNAVAILABLE');
    const asset = mockAssetForGenre(script.genre, script.story_id);
    const duration = await mockAudioDuration(asset);
    const scenes = script.scenes;
    const slice = duration / scenes.length;
    const response: AudioEngineResponse = {
      audio_url: `/api/assets/audio/${asset.audioFile}`,
      duration_seconds: duration,
      scene_markers: scenes.map((scene, index) => ({ scene_id: scene.scene_id, start_seconds: Number((index * slice).toFixed(2)), end_seconds: index === scenes.length - 1 ? duration : Number(((index + 1) * slice).toFixed(2)) })),
      status: 'completed', error: null
    };
    validateAudioResponse(response);
    return response;
  }
}

export class LiveAudioEngineClient implements AudioEngineClient {
  constructor(private readonly url: string) {}
  async renderAudio(script: StoryScript): Promise<AudioEngineResponse> {
    validateStoryResponse(script);
    let response: Response;
    try {
      response = await fetch(this.url, {
        method: 'POST', headers: { 'content-type': 'application/json', 'X-ElevenLabs-API-Key': config.ELEVENLABS_API_KEY! },
        body: JSON.stringify(script), signal: AbortSignal.timeout(600_000)
      });
    }
    catch { throw new AppError(503, 'Could not reach the Audio Engine.', 'AUDIO_ENGINE_UNREACHABLE'); }
    if (!response.ok) throw new AppError(502, `Audio Engine rejected the request (${response.status}).`, 'AUDIO_ENGINE_FAILURE');
    const body: unknown = await response.json();
    try { validateAudioResponse(body); } catch { throw new AppError(502, 'Audio Engine returned an invalid contract response.', 'AUDIO_ENGINE_CONTRACT_ERROR'); }
    const rendered = body as AudioEngineResponse;
    if (rendered.audio_url.startsWith('/files/')) {
      const filePath = rendered.audio_url.slice('/files/'.length);
      if (filePath.split('/').some((segment) => !segment || segment === '.' || segment === '..')) throw new AppError(502, 'Audio Engine returned an unsafe file path.', 'AUDIO_ENGINE_PATH_INVALID');
      rendered.audio_url = `/api/generated-audio/${filePath}`;
    }
    return rendered;
  }
}
export const createAudioEngineClient = (): AudioEngineClient => config.AUDIO_ENGINE_MODE === 'live'
  ? new LiveAudioEngineClient(config.AUDIO_ENGINE_URL!) : new MockAudioEngineClient();
