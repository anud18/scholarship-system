import { randomUUID } from 'crypto';

// In-memory store for email preview HTML (single-instance Docker deployment)
// Previews expire after 10 minutes to limit memory use
const store = new Map<string, string>();

const TTL_MS = 10 * 60 * 1000;

export function storePreview(html: string): string {
  const id = randomUUID();
  store.set(id, html);
  setTimeout(() => store.delete(id), TTL_MS);
  return id;
}

export function getPreview(id: string): string | undefined {
  return store.get(id);
}
