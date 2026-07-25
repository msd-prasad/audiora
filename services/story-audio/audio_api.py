"""HTTP wrapper around the ElevenLabs + FFmpeg timeline renderer.

The Node backend owns secrets and forwards the ElevenLabs key in a request header.
This service never writes the key to disk.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE.parents[1] / ".env", override=True)
RENDERER = Path(os.getenv("AUDIO_RENDERER_PATH", HERE / "render_story_timeline_elevenlabs.py"))
SOUNDS = Path(os.getenv("SOUND_LIBRARY_ROOT", HERE / "sounds"))
OUTPUTS = Path(os.getenv("AUDIO_OUTPUT_ROOT", HERE / "rendered"))
VOICE_MAP = os.getenv("ELEVENLABS_VOICE_MAP", "")
OUTPUTS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Audiora Audio Renderer", version="1.0.0")
app.mount("/files", StaticFiles(directory=OUTPUTS), name="files")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/render-audio")
def render_audio(story: dict, x_elevenlabs_api_key: str | None = Header(default=None)) -> dict:
    return render_story(story, x_elevenlabs_api_key or os.getenv("ELEVENLABS_API_KEY"))


def render_story(story: dict, api_key: str | None = None) -> dict:
    """Render one story for the unified FastAPI API or the standalone worker."""
    api_key = os.getenv("ELEVENLABS_API_KEY") or api_key 
    if not api_key:
        raise HTTPException(status_code=401, detail="ELEVENLABS_API_KEY is required.")
    if not RENDERER.is_file():
        raise HTTPException(status_code=500, detail=f"Renderer not found: {RENDERER}")
    if not SOUNDS.is_dir():
        raise HTTPException(status_code=500, detail=f"Sound library not found: {SOUNDS}")
    job_id = uuid4().hex
    job_dir = OUTPUTS / job_id
    job_dir.mkdir()
    story_file = job_dir / "story.json"
    story_file.write_text(json.dumps(story), encoding="utf-8")
    environment = os.environ.copy()
    environment["ELEVENLABS_API_KEY"] = api_key
    command = [sys.executable, str(RENDERER), str(story_file), "--sounds", str(SOUNDS), "--output", str(job_dir)]
    if VOICE_MAP:
        command.extend(["--voice-map", VOICE_MAP])
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=600, env=environment)
    except subprocess.TimeoutExpired as error:
        raise HTTPException(status_code=504, detail="Audio rendering timed out.") from error
    except subprocess.CalledProcessError as error:
        raise HTTPException(status_code=502, detail=error.stderr[-1500:] or error.stdout[-1500:] or "Audio rendering failed.") from error
    final = job_dir / f"{story['story_id']}_final.wav"
    timeline = job_dir / "timeline.json"
    if not final.is_file() or not timeline.is_file():
        raise HTTPException(status_code=502, detail="Audio renderer did not create its expected output.")
    data = json.loads(timeline.read_text(encoding="utf-8"))
    # The Node backend serves this folder. Leave only the finished WAV public;
    # dialogue assets, the source story JSON, and timeline details stay private.
    for child in job_dir.iterdir():
        if child == final:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    return {
        "audio_url": f"/files/{job_id}/{final.name}",
        "duration_seconds": data["duration_seconds"],
        "scene_markers": data["scene_markers"],
        "status": "completed",
        "error": None,
    }
