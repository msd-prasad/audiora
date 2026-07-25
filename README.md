# Audiora

Audiora turns a prompt, a book title, or a remembered dream into a cinematic audio-story workflow. This repository is a TypeScript monorepo: `frontend/` is the Vite/React player experience and `backend/` is the orchestration service.

## Run locally

1. Copy `.env.example` to `.env`. An OpenAI key is optional in mock mode; without one, Phase 1 uses an isolated local formatter so the whole product remains demoable.
2. Run `pnpm install` from the repository root.
3. Run `pnpm --filter @audiora/backend run generate:assets` once to create the original local MP3 fixtures.
4. Run `pnpm dev`, then open `http://localhost:5173`.

The frontend proxies `/api` to the backend at `http://localhost:8787`. Set `VITE_API_URL` if it is hosted separately.

## Live Python audio services

The complete OpenAI story preprocessor, ElevenLabs renderer, sound catalogue, and local sound library live in [`services/story-audio/`](./services/story-audio/). Generated dialogue clips and final WAV files are intentionally ignored by Git.

Install the Python service dependencies and ensure `ffmpeg`/`ffprobe` are available on your `PATH`:

```bash
python3 -m venv .venv-audio
.venv-audio/bin/pip install -r services/story-audio/requirements.txt
```

For live mode, set `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`, `STORY_ENGINE_MODE=live`, and `AUDIO_ENGINE_MODE=live` in `.env`. In separate terminals, start the services and app:

```bash
.venv-audio/bin/uvicorn main:app --app-dir services/story-audio --port 8000
.venv-audio/bin/uvicorn audio_api:app --app-dir services/story-audio --port 8001
pnpm dev
```

The Node backend forwards each key only to its matching local service. The browser receives only the final backend-served audio URL, never API keys or the renderer's intermediate files.

## Engine boundary

The public contracts live in [`contracts/story-engine.schema.json`](./contracts/story-engine.schema.json) and [`contracts/audio-engine.schema.json`](./contracts/audio-engine.schema.json). The backend validates payloads on both sides of each adapter.

| Service | Mock mode | Live switch |
| --- | --- | --- |
| Story Engine | `MockStoryEngineClient` emits a deterministic, contract-valid scene script after a configurable 1.5–4 second delay. | Set `STORY_ENGINE_MODE=live` and `STORY_ENGINE_URL=https://…` |
| Audio Engine | `MockAudioEngineClient` supplies original playable MP3 fixtures and contract-valid scene markers after the same delay. | Set `AUDIO_ENGINE_MODE=live` and `AUDIO_ENGINE_URL=https://…` |

`MOCK_ERROR_RATE` (default `0.03`) makes mock calls occasionally fail, so the client’s retry states are exercised honestly. The UI only speaks to orchestration endpoints and never branches on mock data.

## Environment

See [`.env.example`](./.env.example) for every value. `OPENAI_API_KEY` is used only by Phase 1. The default model is `gpt-4.1-mini`; change `OPENAI_MODEL` if your deployment uses a different available model.

## Validation

```bash
pnpm typecheck
pnpm test
pnpm build
```

The adapter integration tests validate the mock output against the exact JSON Schema contracts and ensure the final scene marker meets the fixture duration.

## Mock assets

The four cover images in `backend/mocks/assets/covers/` are original SVG artwork. The companion MP3 fixtures are generated from original tonal synthesis via `backend/scripts/generate-mock-audio.cjs`, so no third-party audio license is needed. The visual-image generation service was unavailable in the development environment; the SVGs keep the same local, swappable asset boundary.
