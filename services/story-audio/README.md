# Immersive Story Generator

This FastAPI service creates an audio-production JSON document from a vague story prompt. It deliberately uses two model passes:

1. a story blueprint expands the prompt into genre, characters, motivations, arc, and listening design;
2. a production pass turns that blueprint into scenes, dialogue, emotional delivery metadata, ambience, music, pauses, and sound-effect cues.

## Setup

Install a current Python 3.10+ runtime, then run:

```powershell
pip install -r requirements.txt
$env:OPENAI_API_KEY = "sk-..."
uvicorn main:app --reload
```

Never put a live key into source control. For local development, copy `.env.example` to the git-ignored `.env` file; the application loads it automatically. In production, set `OPENAI_API_KEY` through the platform's secret manager instead.

## Generate a story

```powershell
$headers = @{ "X-OpenAI-API-Key" = "sk-..." }
$body = @{
  prompt = "A young radio astronomer hears a voice in the static that knows her childhood nickname."
  language = "en"
  target_minutes = 4
  audience = "young adults"
  content_rating = "PG"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/generate-story" -Method Post `
  -ContentType "application/json" -Headers $headers -Body $body
```

Alternatively, omit the header and set `OPENAI_API_KEY` in the process environment. The service never returns the key.

## Sound database integration

`sound_catalog.py` loads the category-first `sound_catalog_index.json` created from the raw manifest. The model receives its category → term → file-path pairs and must select only from them. Every response is additionally constrained to the documented JSON structure, ready for the TTS/mixing service.

The endpoint is documented interactively at `http://127.0.0.1:8000/docs` after startup.

## Preprocess the sound manifest

Use the category-first indexer to make sound selection cheap for the story model:

```powershell
python preprocess_manifest.py "C:\Users\sriya\Downloads\manifest.json" sound_catalog_index.json
```

An entry such as `fantasy/078_teleport.mp3` becomes:

```json
{
  "categories": {
    "fantasy": {
      "teleport": [
        { "file": "fantasy/078_teleport.mp3" }
      ]
    }
  }
}
```

Terms use arrays so multiple suitable recordings can remain available under one label. Your AI should first select a category, then a term, then pass the returned `file` path to the audio database/storage layer.

For dialogue-level effects, `position_start` and `position_end` are fractions of that line's spoken duration. For example, `position_start: 0.5` starts halfway through a two-second line (at 1 second); `position_end: 1.0` ends at the end of the line. `loop_until_sentence_end` tells the mixer to loop a short asset until the dialogue finishes.

## ElevenLabs-ready dialogue

Each response includes `character_backgrounds` before the scenes. A character has `gender`, `personality`, and a descriptive `voice_profile`. Map that profile to a real ElevenLabs voice ID in the downstream TTS service; do not allow the story model to invent voice IDs.

The dialogue `sentence` is a speech-ready string with only brief, natural bracketed delivery cues:

```json
{
  "sentence": "[whispers] We have six minutes left. [sighs] Okay... let's make them count."
}
```

Store `ELEVENLABS_API_KEY` in a Databricks secret when you build the TTS/mixing service. Do not put it in source code, `.env.example`, or generated story JSON.

## Scene audio timeline

Audio is separate from dialogue in each scene's `audio_cues` list. A cue starts and ends against dialogue IDs, so a mixer can keep ambience and music continuous across multiple spoken lines.

```json
{
  "id": "cue_01",
  "kind": "ambience",
  "sound": "forest ambience",
  "file": "nature/004_forest-ambience.mp3",
  "start_dialogue_id": 1,
  "position_start": 0.0,
  "end_dialogue_id": 6,
  "position_end": 1.0,
  "volume": 0.3,
  "loop": true,
  "start_transition": "fade_in",
  "fade_in_ms": 1500,
  "end_transition": "fade_out",
  "fade_out_ms": 1800
}
```

The renderer resolves a cue's boundary from the actual TTS duration of its referenced dialogue. An ambience cue can therefore start with the first line of a scene and remain continuous until the final line without restarting between speakers.
