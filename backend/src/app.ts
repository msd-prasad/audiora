import express, { type NextFunction, type Request, type Response } from 'express';
import cors from 'cors';
import multer from 'multer';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
import { config } from './config.js';
import { AppError } from './errors.js';
import { briefRequestSchema, BriefGenerator } from './services/brief-generator.js';
import { extractPdfText } from './services/pdf.js';
import { createStoryEngineClient } from './adapters/story-engine.js';
import { createAudioEngineClient } from './adapters/audio-engine.js';
import { coverArtFor } from './services/cover-art.js';
import { LocalStorageClient } from './services/storage.js';
import { validateStoryResponse } from './contracts/validation.js';
import type { StoryScript } from './contracts/types.js';

const assetsRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../mocks/assets');
const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const frontendDist = resolve(dirname(fileURLToPath(import.meta.url)), '../../frontend/dist');
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 3 * 1024 * 1024 } });
const buildSchema = z.object({ briefStory: z.string().min(1).max(20000), title: z.string().min(1).max(160), genre: z.string().min(1).max(80) });

export function createApp() {
  const app = express();
  const generator = new BriefGenerator();
  const storyEngine = createStoryEngineClient();
  const audioEngine = createAudioEngineClient();
  const storage = new LocalStorageClient();
  app.use(cors({ origin: config.FRONTEND_ORIGIN.split(',').map((origin) => origin.trim()) }));
  app.use(express.json({ limit: '2mb' }));
  app.use('/api/assets/audio', express.static(resolve(assetsRoot, 'audio'), { maxAge: '1h' }));
  app.use('/api/assets/covers', express.static(resolve(assetsRoot, 'covers'), { maxAge: '1h' }));
  // The Python renderer writes WAVs into this shared local folder. The browser
  // only ever receives this Express-served link, never the renderer URL/path.
  app.use('/api/generated-audio', express.static(resolve(appRoot, config.GENERATED_AUDIO_DIR), { maxAge: '1h' }));

  app.get('/api/health', (_req, res) => res.json({ ok: true, storyEngine: config.STORY_ENGINE_MODE, audioEngine: config.AUDIO_ENGINE_MODE }));
  app.post('/api/story/extract-pdf', upload.single('file'), async (req, res, next) => {
    try {
      if (!req.file) throw new AppError(400, 'Choose a PDF to extract.', 'PDF_FILE_REQUIRED');
      if (req.file.mimetype !== 'application/pdf' && !req.file.originalname.toLowerCase().endsWith('.pdf')) throw new AppError(415, 'Only PDF files are supported.', 'PDF_TYPE_INVALID');
      res.json({ pdfText: await extractPdfText(req.file.buffer) });
    } catch (error) { next(error); }
  });
  app.post('/api/story/generate-brief', async (req, res, next) => {
    try { res.json(await generator.generate(briefRequestSchema.parse(req.body))); }
    catch (error) { next(error); }
  });
  app.post('/api/story/build-script', async (req, res, next) => {
    try { res.json(await storyEngine.buildScript(buildSchema.parse(req.body))); }
    catch (error) { next(error); }
  });
  app.post('/api/story/render-audio', async (req, res, next) => {
    try {
      validateStoryResponse(req.body);
      const script = req.body as StoryScript;
      const audio = await audioEngine.renderAudio(script);
      if (audio.status === 'failed') throw new AppError(502, audio.error ?? 'The Audio Engine did not complete.', 'AUDIO_RENDER_FAILED');
      const coverImageUrl = coverArtFor(script.genre, script.story_id);
      const libraryEntry = await storage.saveStory({ title: script.title, genre: script.genre, coverImageUrl, rendered: { audio, coverImageUrl, script } });
      // The script is already held by the UI from /build-script and is persisted
      // in the library server-side. Keep the rendering response small.
      res.json(audio);
    } catch (error) { next(error); }
  });
  app.get('/api/library', async (_req, res, next) => { try { res.json(await storage.listStories()); } catch (error) { next(error); } });
  app.get('/api/library/:id', async (req, res, next) => {
    try { const entry = await storage.getStory(req.params.id); if (!entry) throw new AppError(404, 'Story not found.', 'STORY_NOT_FOUND'); res.json(entry); }
    catch (error) { next(error); }
  });
  // Local production testing uses one origin: Express serves the React build and
  // its `/api` routes, so browser requests always reach the live backend.
  app.use(express.static(frontendDist));
  app.use((_req, _res, next) => next(new AppError(404, 'Route not found.', 'NOT_FOUND')));
  app.use((error: unknown, _req: Request, res: Response, _next: NextFunction) => {
    if (error instanceof multer.MulterError && error.code === 'LIMIT_FILE_SIZE') return res.status(413).json({ error: 'PDF files must be 3 MB or smaller.', code: 'PDF_TOO_LARGE' });
    if (error instanceof z.ZodError) return res.status(400).json({ error: 'Please check your input and try again.', code: 'VALIDATION_ERROR', details: error.issues });
    if (error instanceof AppError) return res.status(error.status).json({ error: error.message, code: error.code });
    if (error instanceof Error && error.message.includes('contract violation')) return res.status(502).json({ error: 'An internal service returned invalid data.', code: 'CONTRACT_ERROR' });
    console.error(error);
    return res.status(500).json({ error: 'Something unexpected happened. Please retry.', code: 'INTERNAL_ERROR' });
  });
  return app;
}
