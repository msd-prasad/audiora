#!/usr/bin/env python3
"""Render scene-level JSON audio cues after creating a complete dialogue timeline.

Pipeline:
1. Generate every dialogue file with Eleven v3 (keeping [laughing] / [whispers] tags).
2. Measure every generated file and calculate its absolute story position.
3. Resolve each scene's audio_cues from dialogue-relative 0–1 positions.
4. Mix all cues over the finished dialogue timeline and write one final WAV.
"""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

import httpx

API_ROOT = "https://api.elevenlabs.io/v1"
DEFAULT_VOICES = {"Zephyros": "JBFqnCBsd6RMkjVDRZzb", "Elara": "21m00Tcm4TlvDq8ikWAM"}
CAST_POOL = ["JBFqnCBsd6RMkjVDRZzb", "21m00Tcm4TlvDq8ikWAM", "pNInz6obpgDQGcFmaJgB", "EXAVITQu4vr4xnSDxMaL"]
VOLUME = {"soft": .75, "medium-low": .88, "medium": 1.0, "normal": 1.0, "loud": 1.15}
LOCALE_ALIASES = {
    "british": "en-gb", "british english": "en-gb", "english british": "en-gb",
    "american": "en-us", "american english": "en-us", "english american": "en-us",
    "spanish": "es", "spanish spain": "es-es", "castilian": "es-es", "mexican spanish": "es-mx",
    "french": "fr", "german": "de", "italian": "it", "portuguese": "pt",
    "brazilian portuguese": "pt-br", "japanese": "ja", "korean": "ko", "hindi": "hi",
}


def shell(args: list[str]) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def probe(path: Path) -> float:
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path),
    ], text=True).strip())


def setup() -> str:
    missing = [item for item in ("ffmpeg", "ffprobe") if not shutil.which(item)]
    if missing:
        raise SystemExit(f"Missing: {', '.join(missing)}")
    if not (key := os.getenv("ELEVENLABS_API_KEY")):
        raise SystemExit("Set ELEVENLABS_API_KEY before rendering.")
    return key


def voice_map(path: Path | None) -> dict[str, str]:
    return json.loads(path.read_text()) if path else DEFAULT_VOICES.copy()


def locale_voice_map() -> dict[str, str]:
    """Optional JSON map: {"en-gb": "eleven_voice_id", "es": "eleven_voice_id"}."""
    raw = os.getenv("ELEVENLABS_LOCALE_VOICE_MAP", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ELEVENLABS_LOCALE_VOICE_MAP must be valid JSON.") from exc
    if not isinstance(data, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in data.items()):
        raise ValueError("ELEVENLABS_LOCALE_VOICE_MAP must map locale strings to ElevenLabs voice IDs.")
    return {key.strip().lower(): value.strip() for key, value in data.items() if value.strip()}


def locale_key(background: dict) -> str | None:
    language = str(background.get("spoken_language", "")).strip().lower()
    accent = str(background.get("accent", "")).strip().lower()
    for candidate in (accent, f"{language} {accent}".strip(), language):
        if candidate in LOCALE_ALIASES:
            return LOCALE_ALIASES[candidate]
    return None


def assign_default_cast(story: dict, voices: dict[str, str]) -> dict[str, str]:
    """Prefer explicit character and locale voice IDs, then use the stable default cast."""
    cast = dict(voices)
    cast.setdefault("Narrator", CAST_POOL[0])
    backgrounds = {item.get("name"): item for item in story.get("character_backgrounds", []) if item.get("name")}
    locale_voices = locale_voice_map()
    for scene in story["scenes"]:
        for dialogue in scene.get("dialogue", scene.get("dialogues", [])):
            name = dialogue["character"]["name"]
            if name not in cast:
                locale = locale_key(backgrounds.get(name, {}))
                language = str(backgrounds.get(name, {}).get("spoken_language", "")).lower()
                cast[name] = (
                    locale_voices.get(locale or "")
                    or locale_voices.get((locale or "").split("-", 1)[0])
                    or locale_voices.get(language)
                    or CAST_POOL[len(cast) % len(CAST_POOL)]
                )
    return cast


def generate(client: httpx.Client, key: str, item: dict, voices: dict[str, str], target: Path) -> None:
    name = item["character"]["name"]
    if not (voice_id := voices.get(name)):
        raise ValueError(f"No voice ID mapped for {name!r}; pass --voice-map.")
    response = client.post(
        f"{API_ROOT}/text-to-speech/{voice_id}", params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key, "accept": "audio/mpeg"},
        json={"text": item["sentence"], "model_id": "eleven_v3"},
    )
    response.raise_for_status()
    target.write_bytes(response.content)


def normal_position(item: dict, field: str) -> float:
    return min(1.0, max(0.0, float(item.get(field, 0))))


def create_dialogue_timeline(entries: list[dict], output: Path) -> float:
    """Mix delayed dialogue tracks and return its total duration."""
    inputs, filters, labels = ["ffmpeg", "-y"], [], []
    for index, entry in enumerate(entries):
        inputs.extend(["-i", str(entry["file"])])
        metadata = entry["dialogue"].get("metadata", {})
        delay = round(entry["speech_start"] * 1000)
        label = f"d{index}"
        filters.append(f"[{index}:a]volume={VOLUME.get(metadata.get('volume'), 1.0)},adelay={delay}|{delay}[{label}]")
        labels.append(f"[{label}]")
    total = entries[-1]["end"]
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,apad,atrim=duration={total:.3f}[out]")
    shell(inputs + ["-filter_complex", ";".join(filters), "-map", "[out]", "-ar", "44100", "-ac", "2", str(output)])
    return total


def cue_window(cue: dict, timings: dict[str, dict]) -> tuple[float, float]:
    start_item = timings[str(cue["start_dialogue_id"])]
    end_item = timings[str(cue["end_dialogue_id"])]
    start = start_item["speech_start"] + normal_position(cue, "position_start") * start_item["speech_duration"]
    end = end_item["speech_start"] + normal_position(cue, "position_end") * end_item["speech_duration"]
    if end <= start:
        raise ValueError(f"Cue {cue.get('id')} ends before it starts.")
    return start, end


def mix_story(dialogue_track: Path, scenes: list[dict], scene_timings: dict[str, dict], sounds: Path, output: Path, total: float) -> list[dict]:
    inputs, filters, labels = ["ffmpeg", "-y", "-i", str(dialogue_track)], ["[0:a]volume=1[dialogue]"], ["[dialogue]"]
    exported_cues = []
    input_index = 1
    for scene in scenes:
        timings = scene_timings.get(str(scene["scene_id"]), {})
        for cue in scene.get("audio_cues", []):
            referenced = {str(cue["start_dialogue_id"]), str(cue["end_dialogue_id"])}
            if not referenced.issubset(timings):
                print(f"warning: cue {cue.get('id')} skipped; its dialogue range is outside this sample")
                continue
            file = sounds / cue["file"]
            if not file.is_file():
                print(f"warning: cue {cue.get('id')} skipped; missing {file}")
                continue
            start, end = cue_window(cue, timings)
            length, delay = end - start, round(start * 1000)
            source = ["-stream_loop", "-1", "-i", str(file)] if cue.get("loop", False) else ["-i", str(file)]
            inputs.extend(source)
            chain = f"[{input_index}:a]atrim=duration={length:.3f},asetpts=PTS-STARTPTS,volume={float(cue.get('volume', .5))}"
            fade_in = min(length, max(0, int(cue.get("fade_in_ms", 0))) / 1000)
            fade_out = min(length, max(0, int(cue.get("fade_out_ms", 0))) / 1000)
            if cue.get("start_transition") == "fade_in" and fade_in:
                chain += f",afade=t=in:st=0:d={fade_in:.3f}"
            if cue.get("end_transition") == "fade_out" and fade_out:
                chain += f",afade=t=out:st={max(0, length - fade_out):.3f}:d={fade_out:.3f}"
            label = f"cue{input_index}"
            filters.append(chain + f",adelay={delay}|{delay}[{label}]")
            labels.append(f"[{label}]")
            exported_cues.append({"id": cue.get("id"), "file": cue["file"], "start_seconds": round(start, 3), "end_seconds": round(end, 3), "loop": bool(cue.get("loop", False))})
            input_index += 1
    filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,apad,atrim=duration={total:.3f}[out]")
    shell(inputs + ["-filter_complex", ";".join(filters), "-map", "[out]", "-ar", "44100", "-ac", "2", str(output)])
    return exported_cues


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate dialogue first, then place scene-level audio cues on the final timeline.")
    parser.add_argument("story_json", type=Path)
    parser.add_argument("--sounds", type=Path, default=Path("story_sounds"))
    parser.add_argument("--output", type=Path, default=Path("rendered_timeline"))
    parser.add_argument("--voice-map", type=Path)
    parser.add_argument("--limit-dialogues", type=int)
    args = parser.parse_args()
    key, story, voices = setup(), json.loads(args.story_json.read_text()), voice_map(args.voice_map)
    voices = assign_default_cast(story, voices)
    args.output.mkdir(parents=True, exist_ok=True)
    dialogue_dir = args.output / "dialogue_mp3"; dialogue_dir.mkdir(exist_ok=True)
    entries, scene_timings, scene_markers, count, cursor = [], {}, [], 0, 0.0
    with httpx.Client(timeout=90) as client:
        for scene in story["scenes"]:
            scene_start = cursor
            per_scene = {}
            for dialogue in scene.get("dialogue", scene.get("dialogues", [])):
                count += 1
                if args.limit_dialogues and count > args.limit_dialogues:
                    break
                file = dialogue_dir / f"{count:03}_scene{scene['scene_id']}_dialogue{dialogue['id']}.mp3"
                print(f"[{count}] generating scene {scene['scene_id']} dialogue {dialogue['id']}")
                generate(client, key, dialogue, voices, file)
                duration = probe(file)
                metadata = dialogue.get("metadata", {})
                speech_start = cursor + max(0, int(metadata.get("pause_before_ms", 0))) / 1000
                entry = {"dialogue": dialogue, "file": file, "speech_start": speech_start, "speech_duration": duration, "end": speech_start + duration + max(0, int(metadata.get("pause_after_ms", 0))) / 1000}
                entries.append(entry); per_scene[str(dialogue["id"])] = entry; cursor = entry["end"]
            scene_timings[str(scene["scene_id"])] = per_scene
            if per_scene:
                scene_markers.append({"scene_id": str(scene["scene_id"]), "start_seconds": round(scene_start, 3), "end_seconds": round(cursor, 3)})
            if args.limit_dialogues and count >= args.limit_dialogues:
                break
    if not entries:
        raise SystemExit("No dialogue was generated.")
    dialogue_track = args.output / "dialogue_timeline.wav"
    total = create_dialogue_timeline(entries, dialogue_track)
    final = args.output / f"{story['story_id']}_final.wav"
    cues = mix_story(dialogue_track, story["scenes"], scene_timings, args.sounds, final, total)
    (args.output / "timeline.json").write_text(json.dumps({"duration_seconds": total, "scene_markers": scene_markers, "cues": cues}, indent=2) + "\n")
    print(f"finished: {final} ({total:.2f}s)")


if __name__ == "__main__":
    main()
