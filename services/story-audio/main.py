"""API for turning a vague idea into an immersive table-read JSON document.

Run locally:
    pip install -r requirements.txt
    $env:OPENAI_API_KEY = "sk-..."       # PowerShell; do not put this in source code
    uvicorn main:app --reload

Then POST to http://127.0.0.1:8000/generate-story.  An X-OpenAI-API-Key header
can be supplied instead of OPENAI_API_KEY for a per-request key.
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv

from sound_catalog import catalog_prompt, valid_sound_pairs


# Loads a local, git-ignored .env for development. Production should provide
# OPENAI_API_KEY through its secret manager/environment instead.
load_dotenv()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GenerateStoryRequest(StrictModel):
    prompt: Annotated[str, Field(min_length=8, max_length=4_000)]
    language: Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")] = "en"
    target_minutes: Annotated[int, Field(ge=1, le=12)] = 4
    audience: Annotated[str, Field(min_length=2, max_length=100)] = "general adult"
    content_rating: Literal["G", "PG", "PG-13"] = "PG"


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


app = FastAPI(title="Immersive Story Generator", version="1.0.0")


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
    """Reject any cue that does not map to a real term/path in the processed manifest."""
    allowed = valid_sound_pairs()
    if not allowed:
        raise HTTPException(status_code=500, detail="No processed sound catalogue was found.")
    selected = []
    for scene in story.scenes:
        dialogue_order = {line.id: index for index, line in enumerate(scene.dialogue)}
        for cue in scene.audio_cues:
            if cue.start_dialogue_id not in dialogue_order or cue.end_dialogue_id not in dialogue_order:
                raise HTTPException(
                    status_code=502,
                    detail=f"Audio cue {cue.id} references a dialogue outside scene {scene.scene_id}.",
                )
            starts_after_end = dialogue_order[cue.start_dialogue_id] > dialogue_order[cue.end_dialogue_id]
            invalid_same_line_range = (
                cue.start_dialogue_id == cue.end_dialogue_id
                and cue.position_start > cue.position_end
            )
            if starts_after_end or invalid_same_line_range:
                raise HTTPException(status_code=502, detail=f"Audio cue {cue.id} has an invalid timeline range.")
            selected.append((cue.sound, cue.file))
    unknown = [pair for pair in selected if pair not in allowed]
    if unknown:
        raise HTTPException(status_code=502, detail=f"Model selected sound not in catalogue: {unknown[0]}")


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
    planning_input = request.model_dump_json()
    try:
        blueprint = structured_response(
            client,
            model,
            "You are a cinematic story architect. Expand the listener's idea into a specific, "
            "emotionally coherent story blueprint. Create a beginning, escalation, turning point, "
            "and resonant ending. Design characters that sound distinct when performed. Do not write "
            "the full script yet; return only the requested JSON.",
            planning_input,
            StoryBlueprint,
        )
        production_input = json.dumps(
            {
                "request": request.model_dump(),
                "blueprint": blueprint.model_dump(),
                "sound_catalog": catalog_prompt(),
            },
            ensure_ascii=False,
        )
        story = structured_response(
            client,
            model,
            "You are an award-winning audio drama writer and sound designer. Convert the supplied "
            "blueprint into an immersive table-read document for text-to-speech and audio mixing. "
            "Write for ears: short speakable sentences, natural contractions, occasional restrained "
            "hesitations such as 'um' only when character-true, and meaningful silence represented by "
            "pause fields. Each dialogue 'sentence' must be a single ElevenLabs-ready speech string: "
            "write spoken words directly and use short bracketed delivery cues only where useful, such "
            "as '[whispers]', '[sarcastically]', '[giggles]', '[sighs]', or '[laughs softly]'. Do not "
            "put production instructions outside the sentence. Before scenes, populate "
            "character_backgrounds with each recurring character's gender, personality, and "
            "voice_profile. A voice_profile is descriptive (for example, 'warm, grounded baritone'); "
            "the audio renderer maps it to a real ElevenLabs voice ID. Build scenes with clear acoustic "
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
