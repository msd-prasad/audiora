import 'dotenv/config';
import { z } from 'zod';

const envSchema = z.object({
  PORT: z.coerce.number().default(8787),
  FRONTEND_ORIGIN: z.string().default('http://localhost:5173'),
  OPENAI_API_KEY: z.string().optional(),
  OPENAI_MODEL: z.string().default('gpt-4.1-mini'),
  STORY_ENGINE_MODE: z.enum(['mock', 'live']).default('mock'),
  STORY_ENGINE_URL: z.string().url().optional(),
  AUDIO_ENGINE_MODE: z.enum(['mock', 'live']).default('mock'),
  AUDIO_ENGINE_URL: z.string().url().optional(),
  MOCK_MIN_DELAY_MS: z.coerce.number().min(0).default(1500),
  MOCK_MAX_DELAY_MS: z.coerce.number().min(0).default(4000),
  MOCK_ERROR_RATE: z.coerce.number().min(0).max(1).default(0.03)
}).superRefine((value, ctx) => {
  if (value.STORY_ENGINE_MODE === 'live' && !value.STORY_ENGINE_URL) ctx.addIssue({ code: 'custom', message: 'STORY_ENGINE_URL is required in live mode' });
  if (value.AUDIO_ENGINE_MODE === 'live' && !value.AUDIO_ENGINE_URL) ctx.addIssue({ code: 'custom', message: 'AUDIO_ENGINE_URL is required in live mode' });
  if (value.MOCK_MIN_DELAY_MS > value.MOCK_MAX_DELAY_MS) ctx.addIssue({ code: 'custom', message: 'MOCK_MIN_DELAY_MS cannot exceed MOCK_MAX_DELAY_MS' });
});

export const config = envSchema.parse(process.env);
