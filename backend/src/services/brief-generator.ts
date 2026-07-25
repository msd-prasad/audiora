import OpenAI from 'openai';
import { z } from 'zod';
import { config } from '../config.js';
import { AppError } from '../errors.js';
import type { BriefRequest, BriefStory } from '../contracts/types.js';

const requestSchema = z.discriminatedUnion('mode', [
  z.object({ mode: z.literal('raw_story'), text: z.string().nullable().optional(), audioTranscript: z.string().nullable().optional(), pdfText: z.string().nullable().optional() }),
  z.object({ mode: z.literal('existing_book'), title: z.string().min(1).max(160), author: z.string().max(120).nullable().optional() }),
  z.object({ mode: z.literal('dreamcast'), text: z.string().nullable().optional(), audioTranscript: z.string().nullable().optional() })
]).superRefine((value, ctx) => {
  if (value.mode !== 'existing_book' && ![value.text, value.audioTranscript, value.mode === 'raw_story' ? value.pdfText : null].some((item) => item?.trim())) ctx.addIssue({ code: 'custom', message: 'Add a typed story, voice transcript, or PDF text.' });
});
const resultSchema = z.object({ briefStory: z.string().min(300).max(900), suggestedTitle: z.string().min(1).max(100), suggestedGenre: z.string().min(1).max(80) });

const sourceFor = (request: BriefRequest) => request.mode === 'existing_book'
  ? `${request.title}${request.author ? ` by ${request.author}` : ''}`
  : [request.text, request.audioTranscript, request.mode === 'raw_story' ? request.pdfText : null].filter((item) => item?.trim()).join('\n\n');

const genreFrom = (source: string, dream = false) => dream ? 'Surreal Dream Drama' : /space|star|planet|alien/i.test(source) ? 'Science Fiction' : /murder|dark|shadow|fear|night/i.test(source) ? 'Mystery Thriller' : /love|heart|romance/i.test(source) ? 'Romantic Drama' : 'Cinematic Drama';
const titleFrom = (source: string, dream = false) => {
  const keyword = source.match(/\b([A-Z][a-z]{3,})\b/)?.[1] ?? (dream ? 'Moonlight' : 'The Horizon');
  return dream ? `Where ${keyword} Sleeps` : `Beyond ${keyword}`;
};

function localFallback(request: BriefRequest): BriefStory {
  const source = sourceFor(request).replace(/\s+/g, ' ').trim();
  const dream = request.mode === 'dreamcast';
  const title = request.mode === 'existing_book' ? `A New View of ${request.title}` : titleFrom(source, dream);
  const genre = genreFrom(source, dream);
  const seed = source.slice(0, 620) || 'an ordinary moment that refuses to stay ordinary';
  const paragraphOne = request.mode === 'existing_book'
    ? `This is an original, spoiler-conscious retelling inspired only by the broad premise of ${source}, built for listening rather than reproducing the book. A person at the center of a difficult change discovers that the world they thought they understood has quietly rearranged itself. Each familiar place becomes charged with possibility, and every conversation seems to point toward a choice they have delayed for too long.`
    : `It begins with ${seed.charAt(0).toLowerCase()}${seed.slice(1)}. At first it feels like a detail that can be ignored, one more strange note in an otherwise recognizable day. But the detail keeps returning, tugging at the edges of every quiet moment until the protagonist understands that it is asking to be followed.`;
  const paragraphs = [
    paragraphOne,
    `The journey moves through rooms, streets, and half-remembered places that seem to answer back. Along the way, a wary companion offers practical advice while another voice insists that caution has already cost too much. Their disagreement gives the story its pulse: one path promises safety, the other honesty. Neither is simple, and both reveal something the protagonist has been trying not to name.`,
    `As the pressure rises, small sensory details become signposts—the hum before a storm, a door left open, a light trembling across glass. The protagonist realizes that the problem is not merely what lies ahead; it is the old version of themselves they will have to leave behind. When they finally speak the truth aloud, the world does not become easy, but it becomes clear.`,
    `In the final movement, the choice is made with no guarantee of applause or certainty. There is only a breath, a step, and a new willingness to meet what comes next. The ending lands on a note of earned wonder: the horizon has not moved, but the person looking at it has. ${dream ? 'The dream dissolves slowly, leaving a beautiful question awake in the morning.' : 'It is a beginning disguised as an ending.'}`
  ];
  return { briefStory: paragraphs.join('\n\n'), suggestedTitle: title, suggestedGenre: genre };
}

export class BriefGenerator {
  async generate(input: unknown): Promise<BriefStory> {
    const request = requestSchema.parse(input) as BriefRequest;
    if (!config.OPENAI_API_KEY) return localFallback(request);
    const source = sourceFor(request);
    const modeInstruction = request.mode === 'dreamcast'
      ? 'Turn this dream into a surreal, emotionally coherent narrative while preserving its uncanny imagery.'
      : request.mode === 'existing_book'
        ? 'Create an original, high-level, spoiler-conscious adaptation brief. Do not quote, reproduce, or closely paraphrase copyrighted text.'
        : 'Shape these notes into a clean, vivid, narratable story with a strong beginning, turn, and resolution.';
    const client = new OpenAI({ apiKey: config.OPENAI_API_KEY });
    try {
      const response = await client.responses.create({
        model: config.OPENAI_MODEL,
        input: [{ role: 'system', content: 'You are Audiora\'s story editor. Return strict JSON only with briefStory (300–800 words), suggestedTitle, and suggestedGenre. Use original prose. No markdown.' }, { role: 'user', content: `${modeInstruction}\n\nSource:\n${source}` }],
        text: { format: { type: 'json_object' } }
      });
      return resultSchema.parse(JSON.parse(response.output_text));
    } catch (error) {
      if (error instanceof z.ZodError) throw new AppError(502, 'The story editor returned an incomplete story. Please retry.', 'BRIEF_CONTRACT_ERROR');
      throw new AppError(502, 'The story editor could not generate a brief. Please retry.', 'BRIEF_GENERATION_FAILED');
    }
  }
}
export const briefRequestSchema = requestSchema;
