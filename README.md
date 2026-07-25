# Audiora

Audiora turns a prompt, a book title, or a remembered dream into a cinematic audio-story workflow. `frontend/` is the Vite/React player experience and `services/story-audio/` is the FastAPI orchestration service.

## Run locally

1. Copy `.env.example` to `.env` and set both server-side API keys.
2. Run `pnpm install` from the repository root.
3. Install Python requirements with `.venv-audio/bin/pip install -r services/story-audio/requirements.txt`.
4. Start FastAPI with `.venv-audio/bin/uvicorn main:app --app-dir services/story-audio --port 8000`.
5. Run `pnpm --filter @audiora/frontend dev`, then open `http://localhost:5173`.

The frontend proxies `/api` to FastAPI at `http://localhost:8000`. API keys are read only by the FastAPI process.

For Databricks Apps deployment, including `app.yaml`, secret resources, durable
Unity Catalog volume storage, and production checks, see
[DEPLOY_DATABRICKS.md](./DEPLOY_DATABRICKS.md).

## Live Python audio services

The complete OpenAI story preprocessor, ElevenLabs renderer, sound catalogue, and local sound library live in [`services/story-audio/`](./services/story-audio/). Generated dialogue clips and final WAV files are intentionally ignored by Git.

Install the Python service dependencies and ensure `ffmpeg`/`ffprobe` are available on your `PATH`:

```bash
python3 -m venv .venv-audio
.venv-audio/bin/pip install -r services/story-audio/requirements.txt
```

Set `OPENAI_API_KEY` and `ELEVENLABS_API_KEY` in `.env`. In separate terminals, start FastAPI and the React app:

```bash
.venv-audio/bin/uvicorn main:app --app-dir services/story-audio --port 8000
pnpm --filter @audiora/frontend dev
```

FastAPI calls OpenAI and ElevenLabs directly. The browser receives only the final FastAPI-served audio URL, never API keys or the renderer's intermediate files.

## Environment

See [`.env.example`](./.env.example) for every value. `OPENAI_API_KEY` and `ELEVENLABS_API_KEY` are used only by FastAPI. The default model is `gpt-4.1-mini`; change `OPENAI_MODEL` if your deployment uses a different available model.

## Validation

```bash
pnpm typecheck
pnpm test
pnpm build
```

The adapter integration tests validate the mock output against the exact JSON Schema contracts and ensure the final scene marker meets the fixture duration.

## Mock assets

The four cover images in `backend/mocks/assets/covers/` are original SVG artwork. The companion MP3 fixtures are generated from original tonal synthesis via `backend/scripts/generate-mock-audio.cjs`, so no third-party audio license is needed. The visual-image generation service was unavailable in the development environment; the SVGs keep the same local, swappable asset boundary.
