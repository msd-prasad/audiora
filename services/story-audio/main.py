"""API for turning a vague idea into an immersive table-read JSON document.

Run locally:
    pip install -r requirements.txt
    $env:OPENAI_API_KEY = "sk-..."       # PowerShell; do not put this in source code
    uvicorn main:app --reload

Then POST to http://127.0.0.1:8000/generate-story.  An X-OpenAI-API-Key header
can be supplied instead of OPENAI_API_KEY for a per-request key.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, model_validator
from dotenv import load_dotenv
from pypdf import PdfReader

from sound_catalog import catalog_prompt
from audio_api import OUTPUTS, SOUNDS, render_story


# Loads the one app-level, git-ignored key file. Production should provide
# these values through its secret manager/environment instead.
HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parents[1]
load_dotenv(APP_ROOT / ".env", override=True)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerateStoryRequest(StrictModel):
    # ``prompt`` remains available for short ideas; ``story`` is for source material.
    prompt: Annotated[str | None, Field(min_length=8, max_length=4_000)] = None
    story: Annotated[str | None, Field(min_length=20, max_length=30_000)] = None
    language: Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")] = "en"
    target_minutes: Annotated[int, Field(ge=1, le=12)] = 4
    audience: Annotated[str, Field(min_length=2, max_length=100)] = "general adult"
    content_rating: Literal["G", "PG", "PG-13"] = "PG"

    @model_validator(mode="after")
    def require_story_input(self) -> "GenerateStoryRequest":
        if not self.prompt and not self.story:
            raise ValueError("Provide either a short prompt or a detailed story.")
        return self

    @property
    def source_type(self) -> str:
        return "detailed_story" if self.story else "rough_idea"

    @property
    def source_text(self) -> str:
        return self.story or self.prompt or ""


class CharacterBlueprint(StrictModel):
    name: str
    role: str
    personality: str
    motivation: str
    voice_direction: str


class SceneBlueprint(StrictModel):
    number: int
    purpose: str
    location: str
    emotional_arc: str


class StoryBlueprint(StrictModel):
    title: str
    genre: str
    logline: str
    detailed_overview: str
    listening_design: str
    themes: list[str]
    characters: list[CharacterBlueprint]
    scene_plan: list[SceneBlueprint]


Gender = Literal["female", "male", "nonbinary", "unspecified"]
Emotion = Literal[
    "calm", "anxious", "angry", "sad", "joyful", "afraid", "hopeful", "tender",
    "suspicious", "determined", "surprised", "whispering",
]
Pace = Literal["very_slow", "slow", "measured", "conversational", "quick"]
Pitch = Literal["low", "normal", "high"]
Volume = Literal["low", "medium", "high"]


class AudioCue(StrictModel):
    """A scene timeline cue, independent of individual dialogue objects."""

    id: str
    kind: Literal["ambience", "music", "sfx"]
    sound: str
    file: str
    start_dialogue_id: int
    position_start: Annotated[float, Field(ge=0, le=1)]
    end_dialogue_id: int
    position_end: Annotated[float, Field(ge=0, le=1)]
    volume: Annotated[float, Field(ge=0, le=1)]
    loop: bool
    start_transition: Literal["fade_in", "abrupt"]
    fade_in_ms: Annotated[int, Field(ge=0, le=10_000)]
    end_transition: Literal["fade_out", "abrupt"]
    fade_out_ms: Annotated[int, Field(ge=0, le=10_000)]


class CharacterVoice(StrictModel):
    name: str
    voice_profile: str


class CharacterBackground(StrictModel):
    """Performance context for the downstream ElevenLabs voice renderer."""

    name: str
    gender: Gender
    personality: str
    spoken_language: str
    accent: str
    voice_profile: str


class DeliveryMetadata(StrictModel):
    emotion: Emotion
    tone: str
    pace: Pace
    pitch: Pitch
    volume: Volume
    pause_before_ms: Annotated[int, Field(ge=0, le=10_000)]
    pause_after_ms: Annotated[int, Field(ge=0, le=10_000)]
    emphasis: list[str]
    reverb: bool


class DialogueLine(StrictModel):
    id: int
    sentence: str
    character: CharacterVoice
    metadata: DeliveryMetadata


class Scene(StrictModel):
    scene_id: int
    title: str
    description: str
    dialogue: list[DialogueLine]
    audio_cues: list[AudioCue]


class GlobalSettings(StrictModel):
    master_volume: float
    default_voice_profile: str
    background_music_volume: float
    sfx_volume: float
    speech_volume: float
    output_format: Literal["mp3", "wav"]
    sample_rate: Literal[22050, 44100, 48000]


class ImmersiveStory(StrictModel):
    story_id: str
    title: str
    genre: str
    language: str
    story_overview: StoryBlueprint
    character_backgrounds: list[CharacterBackground]
    global_settings: GlobalSettings
    scenes: list[Scene]


app = FastAPI(title="Audiora API", version="1.0.0")
origins = [item.strip() for item in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173,http://127.0.0.1:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.mount("/api/generated-audio", StaticFiles(directory=OUTPUTS), name="generated-audio")
COVERS = HERE / "assets" / "covers"
COVER_OUTPUTS = Path(os.getenv("COVER_OUTPUT_ROOT", HERE / "rendered" / "covers"))
COVER_OUTPUTS.mkdir(parents=True, exist_ok=True)
FALLBACK_COVER_URL = "/api/assets/covers/default-cover.svg"
app.mount("/api/assets/covers", StaticFiles(directory=COVERS), name="covers")
app.mount("/api/generated-covers", StaticFiles(directory=COVER_OUTPUTS), name="generated-covers")
FRONTEND_DIST = APP_ROOT / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


def strict_schema(model: type[BaseModel]) -> dict:
    """Make Pydantic's JSON Schema compatible with Structured Outputs strict mode."""
    schema = model.model_json_schema()

    def visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            node["additionalProperties"] = False
            if "properties" in node:
                node["required"] = list(node["properties"])
        for value in node.values():
            if isinstance(value, dict):
                visit(value)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

    visit(schema)
    return schema


def structured_response(client: OpenAI, model: str, instructions: str, payload: str, output: type[BaseModel]) -> BaseModel:
    response = client.responses.create(
        model=model,
        store=False,
        instructions=instructions,
        # JSON mode requires the input message itself to explicitly request JSON.
        input=f"Return valid JSON that follows the requested schema.\n\n{payload}",
        text={
            "format": {
                "type": "json_schema",
                "name": output.__name__.lower(),
                "schema": strict_schema(output),
                "strict": True,
            }
        },
    )
    if not response.output_text:
        raise HTTPException(status_code=502, detail="The model returned no structured story output.")
    return output.model_validate_json(response.output_text)


def validate_sound_references(story: ImmersiveStory) -> None:
    """Keep only cues whose catalog entry and local audio file are available.

    Story generation should still succeed when an optional ambience or SFX asset
    is unavailable; the dialogue timeline remains the source of truth.
    """
    sounds_root = SOUNDS.resolve()
    for scene in story.scenes:
        dialogue_order = {line.id: index for index, line in enumerate(scene.dialogue)}
        usable_cues = []
        for cue in scene.audio_cues:
            if cue.start_dialogue_id not in dialogue_order or cue.end_dialogue_id not in dialogue_order:
                print(f"warning: cue {cue.id} skipped; dialogue range is outside scene {scene.scene_id}")
                continue
            starts_after_end = dialogue_order[cue.start_dialogue_id] > dialogue_order[cue.end_dialogue_id]
            invalid_same_line_range = (
                cue.start_dialogue_id == cue.end_dialogue_id
                and cue.position_start > cue.position_end
            )
            if starts_after_end or invalid_same_line_range:
                print(f"warning: cue {cue.id} skipped; invalid timeline range")
                continue
            sound_path = (SOUNDS / cue.file).resolve()
            if not sound_path.is_relative_to(sounds_root) or not sound_path.is_file():
                print(f"warning: cue {cue.id} skipped; sound file is unavailable: {cue.file}")
                continue
            usable_cues.append(cue)
        scene.audio_cues = usable_cues


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate-story", response_model=ImmersiveStory)
def generate_story(
    request: GenerateStoryRequest,
    x_openai_api_key: Annotated[str | None, Header()] = None,
) -> ImmersiveStory:
    """Create a blueprint first, then turn that blueprint into production-ready audio JSON."""
    api_key = x_openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Set OPENAI_API_KEY or send an X-OpenAI-API-Key request header.",
        )

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4.1")
    planning_input = json.dumps(
        {
            "source_type": request.source_type,
            "source_text": request.source_text,
            "language": request.language,
            "target_minutes": request.target_minutes,
            "audience": request.audience,
            "content_rating": request.content_rating,
        },
        ensure_ascii=False,
    )
    try:
        blueprint = structured_response(
            client,
            model,
            "You are a cinematic story architect. For source_type='rough_idea', expand the listener's "
            "idea into a specific, emotionally coherent story blueprint with a beginning, escalation, "
            "turning point, and resonant ending. For source_type='detailed_story', preserve the supplied "
            "plot, characters, relationships, setting, and stated scene background; only organize it "
            "into scenes and add audio-first performance direction. Do not invent a replacement plot or "
            "major events. Design characters that sound distinct when performed. Do not write the full "
            "script yet; return only the requested JSON.",
            planning_input,
            StoryBlueprint,
        )
        production_input = json.dumps(
            {
                "request": {
                    **request.model_dump(exclude={"prompt", "story"}),
                    "source_type": request.source_type,
                    "source_text": request.source_text,
                },
                "blueprint": blueprint.model_dump(),
                "sound_catalog": catalog_prompt(),
            },
            ensure_ascii=False,
        )
        story = structured_response(
            client,
            model,
            "You are an award-winning audio drama writer and sound designer. Convert the supplied "
            "blueprint and source material into an immersive table-read document for text-to-speech and "
            "audio mixing. When source_type is detailed_story, faithfully adapt its events and visual "
            "background into scenes; do not replace its story with a new one. You may condense, add brief "
            "spoken transitions, and soften details as required by content_rating. "
            "Write for ears: short speakable sentences, natural contractions, occasional restrained "
            "hesitations such as 'um' only when character-true, and meaningful silence represented by "
            "pause fields. Each dialogue 'sentence' must be a single ElevenLabs-ready speech string: "
            "write spoken words directly and use short bracketed delivery cues only where useful, such "
            "as '[whispers]', '[sarcastically]', '[giggles]', '[sighs]', or '[laughs softly]'. Do not "
            "put production instructions outside the sentence. Before scenes, populate "
            "character_backgrounds with each recurring character's gender, personality, spoken_language, accent, and "
            "voice_profile. Preserve the supplied speaking language and accent. Write that character's spoken dialogue "
            "in their spoken_language, unless the story explicitly says they switch languages. A voice_profile is "
            "descriptive (for example, 'warm, grounded baritone with a British English accent'); the audio renderer "
            "maps it to a real ElevenLabs voice ID. Build scenes with clear acoustic "
            "geography and emotional movement. Use only "
            "all audio belongs only in each scene's separate audio_cues timeline—not inside dialogue. "
            "Every audio_cues id is a non-empty string and kind is exactly one of 'ambience', 'music', "
            "or 'sfx'. "
            "Every cue must include its exact matching 'file' path from sound_catalog, a start_dialogue_id, "
            "end_dialogue_id, and position_start/position_end as fractions from 0.0 to 1.0 within those "
            "respective dialogue lines. For a continuous ambience bed, start at position 0.0 of the first "
            "dialogue ID and end at position 1.0 of the last dialogue ID, with loop=true. Choose either "
            "start_transition='fade_in' plus fade_in_ms, or start_transition='abrupt' and fade_in_ms=0; "
            "apply the equivalent rule for end_transition and fade_out_ms. Use fades for natural scene "
            "changes and abrupt transitions only when dramatically justified. Never invent an asset name "
            "or path. Keep dialogue appropriate for the requested rating. Return JSON only.",
            production_input,
            ImmersiveStory,
        )
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Model output did not match the story schema: {exc}") from exc

    story.story_id = f"story_{uuid4().hex[:12]}"
    story.title = blueprint.title
    story.genre = blueprint.genre
    story.language = request.language
    story.story_overview = blueprint
    validate_sound_references(story)
    return story


# The endpoints below replace the former Express orchestration layer. The React
# app calls this FastAPI service directly; API keys remain only in the local
# server environment and are never accepted from the browser.
class CharacterInput(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    gender: Literal["woman", "man", "non-binary", "unspecified"]
    personality: Annotated[str, Field(min_length=1, max_length=240)]
    spoken_language: Annotated[str, Field(min_length=2, max_length=80)]
    accent: Annotated[str, Field(max_length=120)]


class BriefRequest(StrictModel):
    mode: Literal["raw_story", "existing_book", "dreamcast"]
    text: str | None = None
    audioTranscript: str | None = None
    pdfText: str | None = None
    title: str | None = None
    author: str | None = None


class BriefResponse(StrictModel):
    briefStory: str
    suggestedTitle: str
    suggestedGenre: str
    characters: list[CharacterInput]


class BuildScriptRequest(StrictModel):
    briefStory: Annotated[str, Field(min_length=20, max_length=30_000)]
    title: Annotated[str, Field(min_length=1, max_length=160)]
    genre: Annotated[str, Field(min_length=1, max_length=80)]
    characters: list[CharacterInput] = []


LIBRARY_PATH = Path(os.getenv("LIBRARY_STORAGE_PATH", HERE / "storage" / "library.json"))


def brief_source(request: BriefRequest) -> str:
    if request.mode == "existing_book":
        return f"{request.title or ''}{f' by {request.author}' if request.author else ''}".strip()
    return "\n\n".join(value.strip() for value in (request.text, request.audioTranscript, request.pdfText) if value and value.strip())


def read_library() -> list[dict]:
    try:
        return json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_library(entries: list[dict]) -> None:
    LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def cover_prompt(story: dict) -> str:
    """Create cover direction that feels native to Audiora's midnight-and-amber UI."""
    scenes = story.get("scenes") or []
    scene_text = " ".join(
        str(scene.get("description") or scene.get("title") or "")
        for scene in scenes[:2]
    )
    title = str(story.get("title") or "Untitled story")[:160]
    genre = str(story.get("genre") or "cinematic fiction")[:100]
    visual_context = scene_text[:1_200] or "an evocative moment from an original audio story"
    return (
        "Square premium cover artwork for an immersive audio story. "
        "Match Audiora's visual language: midnight indigo and deep plum shadows, "
        "luminous warm amber and soft coral highlights, elegant cinematic atmosphere, "
        "subtle film grain, layered depth, one memorable central visual motif. "
        "No words, letters, typography, logos, UI, watermark, or border. "
        f"Title concept: {title}. Genre: {genre}. Story imagery: {visual_context}"
    )


def generate_cover(story: dict) -> str:
    """Generate a stored thumbnail, falling back without affecting audio delivery."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return FALLBACK_COVER_URL
    try:
        image = OpenAI(api_key=api_key).images.generate(
            model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini"),
            prompt=cover_prompt(story),
            size="1024x1024",
            quality="low",
            output_format="jpeg",
            output_compression=85,
        )
        image_base64 = image.data[0].b64_json if image.data else None
        if not image_base64:
            raise ValueError("The image API returned no thumbnail data.")
        filename = f"cover_{uuid4().hex}.jpg"
        (COVER_OUTPUTS / filename).write_bytes(base64.b64decode(image_base64))
        return f"/api/generated-covers/{filename}"
    except Exception as exc:  # Covers are optional; a render must never fail because artwork does.
        print(f"OpenAI cover generation failed ({type(exc).__name__}): {exc}")
        return FALLBACK_COVER_URL


@app.exception_handler(HTTPException)
async def http_error(_request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.get("/api/health")
def api_health() -> dict[str, object]:
    return {"ok": True, "storyEngine": "live", "audioEngine": "live"}


@app.post("/api/story/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)) -> dict[str, str]:
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")
    data = await file.read()
    if len(data) > 3 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF files must be 3 MB or smaller.")
    try:
        reader = PdfReader(__import__("io").BytesIO(data))
        text = " ".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="We could not read text from that PDF. Try a text-based PDF or paste the story instead.") from exc
    text = " ".join(text.split())
    if not text:
        raise HTTPException(status_code=422, detail="We could not read text from that PDF. Try a text-based PDF or paste the story instead.")
    return {"pdfText": text}


@app.post("/api/story/generate-brief", response_model=BriefResponse)
def generate_brief(request: BriefRequest) -> BriefResponse:
    source = brief_source(request)
    if not source:
        raise HTTPException(status_code=400, detail="Add a typed story, voice transcript, PDF text, or book title.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=401, detail="OPENAI_API_KEY is required for live story generation.")
    instruction = "Turn the supplied source into 350–550 words of original, narratable prose with a clear beginning, turn, and emotionally satisfying ending."
    if request.mode == "existing_book":
        instruction = "Create an original, spoiler-conscious, high-level adaptation brief from the title only; do not quote or reproduce copyrighted material."
    elif request.mode == "dreamcast":
        instruction = "Turn this dream into a surreal, emotionally coherent narratable story while preserving its uncanny imagery."
    payload = json.dumps({"mode": request.mode, "source": source, "instruction": instruction}, ensure_ascii=False)
    try:
        return structured_response(
            OpenAI(api_key=api_key), os.getenv("OPENAI_MODEL", "gpt-4.1"),
            "You are Audiora's story editor. Return only the requested JSON. briefStory must be original prose, "
            "suggestedTitle and suggestedGenre must be concise. For every character include name, gender, "
            "personality, spoken_language (for example, 'Spanish' or 'English'), and accent (for example, "
            "'Mexican Spanish', 'British English', or an empty string when no accent is relevant). Infer these "
            "from the source only when it supports them; never stereotype a character's nationality or ethnicity.",
            payload, BriefResponse,
        )
    except (APIError, ValueError) as exc:
        # Keep the browser response neutral, but retain the provider's safe
        # diagnostic in the server log so a deployment issue can be traced.
        print(f"OpenAI brief generation failed ({type(exc).__name__}): {exc}")
        raise HTTPException(status_code=502, detail="The story editor could not generate a valid brief. Please retry.") from exc


@app.post("/api/story/build-script", response_model=ImmersiveStory)
def build_script(request: BuildScriptRequest) -> ImmersiveStory:
    character_guide = "\n".join(
        f"- {item.name} | {item.gender} | {item.personality} | speaks: {item.spoken_language}"
        f" | accent: {item.accent or 'not specified'}"
        for item in request.characters
    )
    source = f"TITLE: {request.title}\nGENRE: {request.genre}\n"
    if character_guide:
        source += f"CHARACTER GUIDE:\n{character_guide}\n"
    source += f"\nSTORY:\n{request.briefStory}"
    return generate_story(GenerateStoryRequest(story=source))


@app.post("/api/story/render-audio")
def render_audio(story: dict) -> dict:
    result = render_story(story)
    if result["audio_url"].startswith("/files/"):
        result["audio_url"] = "/api/generated-audio/" + result["audio_url"].removeprefix("/files/")
    cover = generate_cover(story)
    result["coverImageUrl"] = cover
    entries = read_library()
    entries.append({
        "id": str(uuid4()), "title": story.get("title", "Untitled story"), "genre": story.get("genre", "Story"),
        "coverImageUrl": cover, "createdAt": datetime.now(timezone.utc).isoformat(),
        "rendered": {"audio": result, "coverImageUrl": cover, "script": story},
    })
    write_library(entries)
    return result


@app.get("/api/library")
def list_library() -> list[dict]:
    return sorted(read_library(), key=lambda entry: entry.get("createdAt", ""), reverse=True)


@app.get("/api/library/{entry_id}")
def get_library(entry_id: str) -> dict:
    for entry in read_library():
        if entry.get("id") == entry_id:
            return entry
    raise HTTPException(status_code=404, detail="Story not found.")


@app.get("/", include_in_schema=False)
@app.get("/{client_path:path}", include_in_schema=False)
def serve_frontend(client_path: str = ""):
    """Serve the built React SPA, including client-side routes such as /player."""
    if client_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Route not found.")
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="Frontend build is missing. Run pnpm --filter @audiora/frontend build.")
    return FileResponse(index)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("UVICORN_HOST", os.getenv("AUDIORA_HOST", "127.0.0.1")),
        port=int(os.getenv("UVICORN_PORT", os.getenv("DATABRICKS_APP_PORT", os.getenv("AUDIORA_PORT", "8000")))),
    )
