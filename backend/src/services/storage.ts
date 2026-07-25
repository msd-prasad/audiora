import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { RenderedStory } from '../contracts/types.js';

export interface LibraryEntry {
  id: string; title: string; genre: string; coverImageUrl: string; createdAt: string; rendered: RenderedStory;
}
export interface StorageClient { listStories(): Promise<LibraryEntry[]>; getStory(id: string): Promise<LibraryEntry | null>; saveStory(story: Omit<LibraryEntry, 'id' | 'createdAt'>): Promise<LibraryEntry>; }
const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const libraryPath = resolve(projectRoot, 'storage/library.json');

export class LocalStorageClient implements StorageClient {
  private async read(): Promise<LibraryEntry[]> {
    try { return JSON.parse(await readFile(libraryPath, 'utf8')) as LibraryEntry[]; }
    catch { return []; }
  }
  private async write(entries: LibraryEntry[]) { await mkdir(dirname(libraryPath), { recursive: true }); await writeFile(libraryPath, JSON.stringify(entries, null, 2)); }
  async listStories() { return (await this.read()).sort((a, b) => b.createdAt.localeCompare(a.createdAt)); }
  async getStory(id: string) { return (await this.read()).find((entry) => entry.id === id) ?? null; }
  async saveStory(story: Omit<LibraryEntry, 'id' | 'createdAt'>) {
    const entries = await this.read();
    const entry: LibraryEntry = { ...story, id: crypto.randomUUID(), createdAt: new Date().toISOString() };
    entries.push(entry); await this.write(entries); return entry;
  }
}
