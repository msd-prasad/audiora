import OpenAI from "openai";
import { z } from "zod";
import { config } from "../config.js";
import { AppError } from "../errors.js";
import type { BriefRequest, BriefStory } from "../contracts/types.js";

const requestSchema = z
  .discriminatedUnion("mode", [
    z.object({
      mode: z.literal("raw_story"),
      text: z.string().nullable().optional(),
      audioTranscript: z.string().nullable().optional(),
      pdfText: z.string().nullable().optional(),
    }),
    z.object({
      mode: z.literal("existing_book"),
      title: z.string().min(1).max(160),
      author: z.string().max(120).nullable().optional(),
    }),
    z.object({
      mode: z.literal("dreamcast"),
      text: z.string().nullable().optional(),
      audioTranscript: z.string().nullable().optional(),
    }),
  ])
  .superRefine((value, ctx) => {
    if (
      value.mode !== "existing_book" &&
      ![
        value.text,
        value.audioTranscript,
        value.mode === "raw_story" ? value.pdfText : null,
      ].some((item) => item?.trim())
    )
      ctx.addIssue({
        code: "custom",
        message: "Add a typed story, voice transcript, or PDF text.",
      });
  });
const storyWordCount = (text: string) =>
  text.trim().split(/\s+/).filter(Boolean).length;
const characterSchema = z.object({
  name: z.string().min(1).max(80),
  gender: z.enum(["woman", "man", "non-binary", "unspecified"]),
  personality: z.string().min(1).max(240),
});
const baseResultSchema = z.object({
  briefStory: z.string().min(1),
  suggestedTitle: z.string().min(2).max(42),
  suggestedGenre: z.string().min(1).max(80),
  characters: z.array(characterSchema).max(6).default([]),
});
const resultSchema = baseResultSchema.extend({
  // The product contract is expressed in words—not characters. The old 900-character
  // ceiling rejected perfectly valid 300–800 word AI stories (usually 2,000+ characters).
  briefStory: z
    .string()
    .refine(
      (story) => storyWordCount(story) >= 300 && storyWordCount(story) <= 800,
      "briefStory must contain 300–800 words",
    ),
});

const sourceFor = (request: BriefRequest) =>
  request.mode === "existing_book"
    ? `${request.title}${request.author ? ` by ${request.author}` : ""}`
    : [
        request.text,
        request.audioTranscript,
        request.mode === "raw_story" ? request.pdfText : null,
      ]
        .filter((item) => item?.trim())
        .join("\n\n");

const genreFrom = (source: string, dream = false) =>
  dream
    ? "Surreal Dream Drama"
    : /space|star|planet|alien/i.test(source)
      ? "Science Fiction"
      : /murder|dark|shadow|fear|night/i.test(source)
        ? "Mystery Thriller"
        : /love|heart|romance/i.test(source)
          ? "Romantic Drama"
          : "Cinematic Drama";
const titleFrom = (source: string, dream = false) => {
  const keyword =
    source.match(/\b([A-Z][a-z]{3,})\b/)?.[1] ??
    (dream ? "Moonlight" : "The Horizon");
  return dream ? `Where ${keyword} Sleeps` : `Beyond ${keyword}`;
};

function fallbackCharacters(source: string) {
  const names = [...new Set(source.match(/\b[A-Z][a-z]{2,}\b/g) ?? [])].slice(0, 3);
  if (names.length) return names.map((name) => ({ name, gender: 'unspecified' as const, personality: 'Observant and emotionally present in the story.' }));
  if (/girlfriend|woman|she\b|her\b/i.test(source)) return [{ name: 'Elena', gender: 'woman' as const, personality: 'Warm, curious, and attentive to the moment.' }];
  return [{ name: 'Alex', gender: 'unspecified' as const, personality: 'Thoughtful and open to the changes ahead.' }];
}

function localFallback(request: BriefRequest): BriefStory {
  const source = sourceFor(request).replace(/\s+/g, " ").trim();
  const dream = request.mode === "dreamcast";
  const title =
    request.mode === "existing_book"
      ? `A New View of ${request.title}`
      : titleFrom(source, dream);
  const genre = genreFrom(source, dream);
  const seed =
    source.slice(0, 620) || "an ordinary moment that refuses to stay ordinary";
  const paragraphOne =
    request.mode === "existing_book"
      ? `This is an original, spoiler-conscious retelling inspired only by the broad premise of ${source}, built for listening rather than reproducing the book. A person at the center of a difficult change discovers that the world they thought they understood has quietly rearranged itself. Each familiar place becomes charged with possibility, and every conversation seems to point toward a choice they have delayed for too long.`
      : `It begins with ${seed.charAt(0).toLowerCase()}${seed.slice(1)}. At first it feels like a detail that can be ignored, one more strange note in an otherwise recognizable day. But the detail keeps returning, tugging at the edges of every quiet moment until the protagonist understands that it is asking to be followed.`;
  const paragraphs = [
    paragraphOne,
    `The journey moves through rooms, streets, and half-remembered places that seem to answer back. Along the way, a wary companion offers practical advice while another voice insists that caution has already cost too much. Their disagreement gives the story its pulse: one path promises safety, the other honesty. Neither is simple, and both reveal something the protagonist has been trying not to name.`,
    `As the pressure rises, small sensory details become signposts—the hum before a storm, a door left open, a light trembling across glass. The protagonist realizes that the problem is not merely what lies ahead; it is the old version of themselves they will have to leave behind. When they finally speak the truth aloud, the world does not become easy, but it becomes clear.`,
    `In the final movement, the choice is made with no guarantee of applause or certainty. There is only a breath, a step, and a new willingness to meet what comes next. The ending lands on a note of earned wonder: the horizon has not moved, but the person looking at it has. ${dream ? "The dream dissolves slowly, leaving a beautiful question awake in the morning." : "It is a beginning disguised as an ending."}`,
  ];
  return {
    briefStory: paragraphs.join("\n\n"),
    suggestedTitle: title,
    suggestedGenre: genre,
    characters: fallbackCharacters(source),
  };
}

export class BriefGenerator {
  async generate(input: unknown): Promise<BriefStory> {
    const request = requestSchema.parse(input) as BriefRequest;
    if (!config.OPENAI_API_KEY) return localFallback(request);
    const source = sourceFor(request);
    const modeInstruction =
      request.mode === "dreamcast"
        ? "Turn this dream into a surreal, emotionally coherent narrative while preserving its uncanny imagery."
        : request.mode === "existing_book"
          ? "Create an original, high-level, spoiler-conscious adaptation brief. Do not quote, reproduce, or closely paraphrase copyrighted text."
          : "Shape these notes into a clean, vivid, narratable story with a strong beginning, turn, and resolution.";
    const client = new OpenAI({ apiKey: config.OPENAI_API_KEY });
    try {
      const response = await client.responses.create({
        model: config.OPENAI_MODEL,
        input: [
          {
            role: "system",
            content: `You are Audiora's story editor. Return strict JSON only with briefStory, suggestedTitle, and suggestedGenre.\n\nbriefStory must be 350–550 words of original, narratable prose with a clear beginning, turn, and emotionally satisfying ending. Write in very simple, modern English that sounds naturally human-written. Use familiar everyday words, clear sentences, and a warm, direct narration style. Avoid archaic, old-fashioned, ornate, theatrical, overly poetic, overly formal, or slang-heavy language. Do not use speech-like filler or unnecessary dialogue.\n\nTreat the source as canonical. Preserve meaningful details about each character (names, traits, motives, relationships, actions, and stakes) and their world (place, time, weather, objects, sensory details, and atmosphere). Keep concrete details instead of replacing them with vague generalities. Do not invent important facts merely to make the story more dramatic.\n\nNever use markdown or include commentary outside JSON.`,
          },
          {
            role: "system",
            content: "The JSON must also include a characters array. Extract every distinct person the source makes meaningful, up to six. Each item must contain name, gender, and personality. Preserve names explicitly provided by the source. When an important person has no name, give them a simple, suitable name and use it consistently in briefStory. Gender must be one of woman, man, non-binary, or unspecified; use unspecified when the source does not make it clear. Give each personality a short, plain-English description. The characters array is the review-screen header, so do not put a character list inside briefStory.",
          },
          {
            role: "system",
            content: "suggestedTitle must be a short, catchy, natural title of two to five words and no more than 42 characters. Make it specific to the story's strongest image, place, or emotional turn. It should feel like a real book or audio drama title, not a generic summary, slogan, question, subtitle, or long phrase.",
          },
          { role: "user", content: `${modeInstruction}\n\nSource:\n${source}` },
        ],
        max_output_tokens: 2600,
        text: { format: { type: "json_object" } },
      });
      try {
        return resultSchema.parse(JSON.parse(response.output_text));
      } catch (firstValidationError) {
        if (!(firstValidationError instanceof z.ZodError)) throw firstValidationError;
        // If the model misses the word-count contract, repair its draft once instead
        // of forcing the listener to submit the same source again.
        console.warn('[Audiora] Phase 1 draft missed the word-count contract; requesting a repair.');
        const repair = await client.responses.create({
          model: config.OPENAI_MODEL,
          input: [
            {
              role: "system",
              content: "You are Audiora's story editor. Return strict JSON only with briefStory, suggestedTitle, suggestedGenre, and characters. Replace the prior draft with a complete original story of 380 to 520 words; silently count the words before responding. Use very simple, modern English that reads naturally and was written by a person. Avoid archaic, ornate, theatrical, overly poetic, overly formal, or slang-heavy language. Preserve all meaningful character details, relationships, actions, stakes, place, time, weather, objects, sensory details, and atmosphere from the source. characters must be an array of up to six items with name, gender (woman, man, non-binary, or unspecified), and personality. Use each assigned name consistently in briefStory. suggestedTitle must be catchy, natural, two to five words, and no more than 42 characters. Do not add major facts or commentary outside JSON.",
            },
            { role: "user", content: `${modeInstruction}\n\nSource:\n${source}\n\nPrevious draft to repair:\n${response.output_text}` },
          ],
          max_output_tokens: 2600,
          text: { format: { type: "json_object" } },
        });
        const repairedDraft = JSON.parse(repair.output_text);
        try {
          return resultSchema.parse(repairedDraft);
        } catch (secondValidationError) {
          if (!(secondValidationError instanceof z.ZodError)) throw secondValidationError;
          console.warn('[Audiora] Phase 1 repair missed the word-count contract; requesting an expansion.');
          const expansion = await client.responses.create({
            model: config.OPENAI_MODEL,
            input: [
              {
                role: "system",
                content: "You are completing an Audiora story expansion. Return strict JSON only with briefStory, suggestedTitle, suggestedGenre, and characters. The briefStory must be a complete 380 to 520 word narration. Silently count the words. Preserve all concrete details from the source and draft, including people, setting, atmosphere, actions, and relationships. characters must be an array of up to six items with name, gender (woman, man, non-binary, or unspecified), and personality. Use each assigned name consistently in briefStory. suggestedTitle must be catchy, natural, two to five words, and no more than 42 characters. Use simple, natural modern English. No archaic, ornate, slang-heavy, or theatrical wording. Do not add commentary outside JSON.",
              },
              { role: "user", content: `${modeInstruction}\n\nSource:\n${source}\n\nDraft to expand:\n${repair.output_text}` },
            ],
            max_output_tokens: 2600,
            text: { format: { type: "json_object" } },
          });
          const expandedDraft = JSON.parse(expansion.output_text);
          try {
            return resultSchema.parse(expandedDraft);
          } catch (finalValidationError) {
            if (!(finalValidationError instanceof z.ZodError)) throw finalValidationError;
            // The response still has a valid contract shape, but missed only the
            // editorial word target. Returning it is better than blocking the flow.
            console.warn('[Audiora] Phase 1 expansion missed the word-count target; returning its valid AI draft.');
            return baseResultSchema.parse(expandedDraft);
          }
        }
      }
    } catch (error) {
      if (error instanceof z.ZodError)
        throw new AppError(
          502,
          "The story editor returned an incomplete story. Please retry.",
          "BRIEF_CONTRACT_ERROR",
        );
      throw new AppError(
        502,
        "The story editor could not generate a brief. Please retry.",
        "BRIEF_GENERATION_FAILED",
      );
    }
  }
}
export const briefRequestSchema = requestSchema;
