import { create } from 'zustand';
import type { BriefStory, InputMode, RenderedStory } from './types';
type State = { mode: InputMode | null; brief: BriefStory | null; rendered: RenderedStory | null; setMode: (mode: InputMode) => void; setBrief: (brief: BriefStory) => void; setRendered: (rendered: RenderedStory) => void; reset: () => void; };
export const useStoryStore = create<State>((set) => ({ mode: null, brief: null, rendered: null, setMode: (mode) => set({ mode }), setBrief: (brief) => set({ brief }), setRendered: (rendered) => set({ rendered }), reset: () => set({ mode: null, brief: null, rendered: null }) }));
