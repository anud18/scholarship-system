/**
 * Pure resolver for a file's preview URL, extracted from `FileUpload` so the
 * preference logic can be unit-tested without rendering the component (whose
 * jest suite is skipped due to a useEffect/timer issue).
 *
 * Encodes the PR #885 / #892 contract:
 * - prefer a caller-set same-origin `url` (e.g. a /api/v1/preview proxy URL);
 * - else a same-origin/relative `file_path` (never an absolute cross-origin URL
 *   such as a misconfigured http://localhost:8000 file_path on staging, nor a
 *   bare local filename — both render blank in an iframe);
 * - else an object URL for a real local Blob;
 * - else `undefined` — a restored uploaded entry is a plain object (not a Blob),
 *   so calling URL.createObjectURL on it would throw a TypeError.
 */
export interface UploadedFileLike {
  id?: string | number;
  url?: string;
  file_path?: string;
}

/** True when the object carries server-side upload metadata (id / url / file_path). */
export function isUploadedFileLike(file: unknown): boolean {
  const f = file as UploadedFileLike | null | undefined;
  return Boolean(f && (f.id || f.file_path || f.url));
}

export function resolveFilePreviewUrl(file: File, origin: string): string | undefined {
  if (isUploadedFileLike(file)) {
    const uploaded = file as unknown as UploadedFileLike;
    if (uploaded.url) return uploaded.url;
    const fp = uploaded.file_path;
    if (fp && (fp.startsWith("/") || fp.startsWith(origin))) {
      return fp;
    }
    // Restored uploaded entries are plain objects (not real Blobs), so
    // URL.createObjectURL would throw — return undefined and let the caller
    // skip opening the preview.
    if (!(file instanceof Blob)) return undefined;
    return URL.createObjectURL(file);
  }
  // A freshly-selected local file.
  return URL.createObjectURL(file);
}
