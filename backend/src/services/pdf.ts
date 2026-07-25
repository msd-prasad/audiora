import pdf from 'pdf-parse';
import { AppError } from '../errors.js';
export async function extractPdfText(buffer: Buffer) {
  try {
    const parsed = await pdf(buffer);
    const text = parsed.text.replace(/\s+/g, ' ').trim();
    if (!text) throw new Error('No text');
    return text;
  } catch { throw new AppError(422, 'We could not read text from that PDF. Try a text-based PDF or paste the story instead.', 'PDF_EXTRACTION_FAILED'); }
}
