import AjvModule from 'ajv/dist/2020.js';
import type { ValidateFunction } from 'ajv';
import storySchema from '../../../contracts/story-engine.schema.json' with { type: 'json' };
import audioSchema from '../../../contracts/audio-engine.schema.json' with { type: 'json' };
import type { AudioEngineResponse, StoryEngineRequest, StoryScript } from './types.js';

// Ajv's NodeNext declaration is a CJS namespace even though its ESM default is constructable.
const Ajv = AjvModule as unknown as new (options: { allErrors: boolean; strict: boolean }) => {
  addSchema(schema: unknown): void;
  compile(schema: unknown): ValidateFunction;
  errorsText(errors: unknown): string;
};
const ajv = new Ajv({ allErrors: true, strict: false });
ajv.addSchema(storySchema);
ajv.addSchema(audioSchema);
const storyRequest = ajv.compile({ $ref: 'https://audiora.dev/contracts/story-engine.schema.json#/$defs/request' });
const audioResponse = ajv.compile({ $ref: 'https://audiora.dev/contracts/audio-engine.schema.json#/$defs/response' });

function assertContract<T>(validator: ValidateFunction, value: unknown, label: string): asserts value is T {
  if (!validator(value)) throw new Error(`${label} contract violation: ${ajv.errorsText(validator.errors)}`);
}
export const validateStoryRequest: (value: unknown) => asserts value is StoryEngineRequest = (value) => assertContract<StoryEngineRequest>(storyRequest, value, 'Story Engine request');
// The live Python preprocessor owns the richer timeline schema (dialogue + audio_cues).
// Keep the UI boundary deliberately small: all downstream code needs a titled story with scenes.
export const validateStoryResponse: (value: unknown) => asserts value is StoryScript = (value) => {
  if (!value || typeof value !== 'object') throw new Error('Story Engine response contract violation: expected an object');
  const story = value as { story_id?: unknown; title?: unknown; genre?: unknown; language?: unknown; scenes?: unknown };
  if (typeof story.story_id !== 'string' || typeof story.title !== 'string' || typeof story.genre !== 'string' || typeof story.language !== 'string' || !Array.isArray(story.scenes) || !story.scenes.length) {
    throw new Error('Story Engine response contract violation: missing story fields or scenes');
  }
};
export const validateAudioResponse: (value: unknown) => asserts value is AudioEngineResponse = (value) => assertContract<AudioEngineResponse>(audioResponse, value, 'Audio Engine response');
