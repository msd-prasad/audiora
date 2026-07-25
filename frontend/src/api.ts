const base = import.meta.env.VITE_API_URL ?? '';
export const assetUrl = (url: string) => url.startsWith('http') ? url : `${base}${url}`;
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, { headers: { 'content-type': 'application/json', ...(options?.headers ?? {}) }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error ?? 'Something went wrong. Please retry.');
  return body as T;
}
export async function uploadPdf(file: File) {
  const data = new FormData(); data.append('file', file);
  const response = await fetch(`${base}/api/story/extract-pdf`, { method: 'POST', body: data });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error ?? 'We could not read that PDF.');
  return body as { pdfText: string };
}
