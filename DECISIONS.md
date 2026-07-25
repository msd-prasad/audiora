# Audiora implementation decisions

- The two external engines are hidden behind backend adapters. UI code consumes only orchestration responses, so a `mock` → `live` environment change does not alter client behavior.
- Phase 3's external response stays exactly within `contracts/audio-engine.schema.json`. Cover art is workflow presentation metadata supplied by the orchestrator, not an Audio Engine field.
- OpenAI is used for Phase 1 when `OPENAI_API_KEY` is available. A deterministic, clearly isolated local formatter lets the app stay runnable during mock-only development without a key.
- Mock audio assets are short original generated fixtures. Their duration is read from a manifest produced with the asset, avoiding a client assumption about their length.
- Local persistence is intentionally minimal JSON via `StorageClient`. It can be replaced with blob/database storage without touching routing or UI.
