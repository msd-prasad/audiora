export type InputMode = 'raw_story' | 'existing_book' | 'dreamcast';

export type BriefRequest =
  | { mode: 'raw_story'; text?: string | null; audioTranscript?: string | null; pdfText?: string | null }
  | { mode: 'existing_book'; title: string; author?: string | null }
  | { mode: 'dreamcast'; text?: string | null; audioTranscript?: string | null };

export interface BriefStory {
  briefStory: string;
  suggestedTitle: string;
  suggestedGenre: string;
}

export interface StoryEngineRequest { briefStory: string; title: string; genre: string; }
export interface StoryScript {
  story_id: string;
  title: string;
  genre: string;
  language: string;
  global_settings: {
    master_volume: number; default_voice: string; background_music_volume: number;
    sfx_volume: number; speech_volume: number; output_format: 'mp3'; sample_rate: number;
  };
  scenes: Scene[];
}
export interface Scene {
  scene_id: string; title: string; description: string;
  ambience: Array<{ sound: string; volume: number; loop: boolean; interval: number }>;
  background_music: { track: string; volume: number; fade_in_ms: number; fade_out_ms: number };
  dialogue: Dialogue[];
}
export interface Dialogue {
  id: string; sentence: string;
  character: { name: string; voice: string };
  metadata: { emotion: string; tone: string; pace: number; pitch: number; volume: number; pause_before_ms: number; pause_after_ms: number; emphasis: 'none' | 'low' | 'medium' | 'high'; reverb: 'none' | 'light' | 'medium' | 'heavy' };
  background_sounds: Array<{ sound: string; start_offset_ms: number; duration_ms: number; volume: number }>;
}
export interface AudioEngineResponse {
  audio_url: string;
  duration_seconds: number;
  scene_markers: Array<{ scene_id: string; start_seconds: number; end_seconds: number }>;
  status: 'completed' | 'failed';
  error: string | null;
}
export interface RenderedStory {
  audio: AudioEngineResponse;
  coverImageUrl: string;
  script: StoryScript;
}
