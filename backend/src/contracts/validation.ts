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
const storyResponse = ajv.compile({ $ref: 'https://audiora.dev/contracts/story-engine.schema.json#/$defs/response' });
const audioResponse = ajv.compile({ $ref: 'https://audiora.dev/contracts/audio-engine.schema.json#/$defs/response' });

function assertContract<T>(validator: ValidateFunction, value: unknown, label: string): asserts value is T {
  if (!validator(value)) throw new Error(`${label} contract violation: ${ajv.errorsText(validator.errors)}`);
}
export const validateStoryRequest = (value: unknown) => assertContract<StoryEngineRequest>(storyRequest, value, 'Story Engine request');
export const validateStoryResponse = (value: unknown) => assertContract<StoryScript>(storyResponse, value, 'Story Engine response');
export const validateAudioResponse = (value: unknown) => assertContract<AudioEngineResponse>(audioResponse, value, 'Audio Engine response');
