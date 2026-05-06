// Pin the store to globalThis so it is shared across Next.js route bundles.
// Each API route is compiled into its own bundle; a plain module-level Map
// would be duplicated, making POST and GET handlers see different Maps.
const g = globalThis as typeof globalThis & {
  __emailPreviewStore?: Map<string, string>;
};
if (!g.__emailPreviewStore) {
  g.__emailPreviewStore = new Map<string, string>();
}
const store = g.__emailPreviewStore;

const TTL_MS = 10 * 60 * 1000;

function generateId(): string {
  // Prefer Web Crypto API (Node ≥ 19, Edge Runtime, browsers).
  // Fall back to require('crypto') for Node 18 where globalThis.crypto
  // exists but randomUUID may not be exposed as a global.
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { randomUUID } = require('crypto') as { randomUUID: () => string };
  return randomUUID();
}

export function storePreview(html: string): string {
  const id = generateId();
  store.set(id, html);
  setTimeout(() => store.delete(id), TTL_MS);
  return id;
}

export function getPreview(id: string): string | undefined {
  return store.get(id);
}
