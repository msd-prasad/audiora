import { describe, expect, it } from 'vitest';
import { MockStoryEngineClient } from '../src/adapters/story-engine.js';
import { MockAudioEngineClient } from '../src/adapters/audio-engine.js';
import { validateAudioResponse, validateStoryResponse } from '../src/contracts/validation.js';

describe('mock engine adapters', () => {
  const request = { title: 'The Last Signal', genre: 'Science Fiction', briefStory: 'A patient radio operator hears a voice from a future she thought was lost. She follows its instructions through a rain-soaked city and learns that courage is a signal too.' };
  it('emits a deterministic Story Engine script that conforms to the public contract', async () => {
    const client = new MockStoryEngineClient();
    const first = await client.buildScript(request);
    const second = await client.buildScript(request);
    validateStoryResponse(first);
    expect(first).toEqual(second);
    expect(first.scenes.length).toBeGreaterThanOrEqual(3);
  });
  it('renders legal scene markers spanning the real fixture duration', async () => {
    const script = await new MockStoryEngineClient().buildScript(request);
    const audio = await new MockAudioEngineClient().renderAudio(script);
    validateAudioResponse(audio);
    expect(audio.scene_markers.at(0)?.start_seconds).toBe(0);
    expect(audio.scene_markers.at(-1)?.end_seconds).toBe(audio.duration_seconds);
  });
  it('uses character names supplied through the Phase 2 brief-story header', async () => {
    const script = await new MockStoryEngineClient().buildScript({
      ...request,
      briefStory: 'CHARACTER GUIDE\n- Elena | woman | Warm and decisive.\n- Samir | man | Careful and observant.\n\nSTORY\nElena and Samir follow a strange radio signal through the rain-soaked city.'
    });
    expect(['Elena', 'Samir']).toContain(script.scenes[0].dialogue[1].character.name);
    expect(script.scenes[0].dialogue[0].sentence).toContain('Elena and Samir');
  });
});
