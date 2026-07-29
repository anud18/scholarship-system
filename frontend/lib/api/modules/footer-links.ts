/**
 * Footer Links API Module (相關連結)
 *
 * Admin-managed entries rendered in the site footer. Each link is either an
 * external URL or an uploaded document (PDF / Office / ODF) streamed back
 * through the backend proxy — never a direct MinIO URL.
 */

import type { ApiResponse } from '../types';

export type FooterLinkType = 'url' | 'file';

/** Footer link payload returned by the backend. */
export type FooterLink = {
  id: number;
  title_zh: string;
  title_en: string | null;
  link_type: FooterLinkType;
  url: string | null;
  object_name: string | null;
  original_filename: string | null;
  content_type: string | null;
  file_size: number | null;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type FooterLinkCreatePayload = {
  title_zh: string;
  title_en?: string | null;
  url: string;
  is_active?: boolean;
};

export type FooterLinkUpdatePayload = {
  title_zh?: string;
  title_en?: string | null;
  url?: string;
  is_active?: boolean;
};

/**
 * Broadcast name for "the footer link list changed".
 *
 * The admin panel and the <Footer> render on the SAME page (the panel lives
 * inside the 系統管理 tab; the footer is mounted outside <Tabs> and stays
 * mounted for the whole session), but they hold independent copies of the
 * list. Without this signal an admin who adds or hides a link and scrolls
 * down sees the mount-time snapshot and concludes the save failed.
 */
export const FOOTER_LINKS_CHANGED_EVENT = "footer-links:changed";

/** Tell any mounted <Footer> to refetch. No-op during SSR. */
export function notifyFooterLinksChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(FOOTER_LINKS_CHANGED_EVENT));
}

function authToken(): string {
  return typeof window !== 'undefined'
    ? localStorage.getItem('auth_token') || ''
    : '';
}

function jsonHeaders(): Record<string, string> {
  return {
    Authorization: `Bearer ${authToken()}`,
    'Content-Type': 'application/json',
  };
}

/**
 * Build the file-proxy URL for a file-backed footer link. Mirrors
 * buildSuppDocFileProxyUrl but routes via /api/v1/preview/footer-links?id=...
 *
 * The cache-buster is derived from the stored object name so replacing a
 * link's file bypasses the browser cache.
 */
export function buildFooterLinkFileProxyUrl(
  id: number,
  objectName?: string | null
): string {
  const cacheBuster = encodeURIComponent(
    (objectName || '').split('/').pop() || String(id)
  );
  return `/api/v1/preview/footer-links?id=${id}&token=${encodeURIComponent(
    authToken()
  )}&v=${cacheBuster}`;
}

/**
 * Resolve the href a footer entry should point at: the external URL for
 * `url` links, or the streaming proxy URL for `file` links.
 */
export function footerLinkHref(link: FooterLink): string {
  if (link.link_type === 'file') {
    return buildFooterLinkFileProxyUrl(link.id, link.object_name);
  }
  return link.url || '#';
}

/** Label for the given locale, falling back to the Chinese title. */
export function footerLinkLabel(link: FooterLink, locale: 'zh' | 'en'): string {
  if (locale === 'en') return link.title_en || link.title_zh;
  return link.title_zh;
}

export function createFooterLinksApi() {
  return {
    /**
     * List footer links. `includeInactive` is honoured for admins only —
     * the backend always filters hidden links out for non-admins.
     */
    list: async (
      includeInactive = false
    ): Promise<ApiResponse<FooterLink[]>> => {
      const query = includeInactive ? '?include_inactive=true' : '';
      const res = await fetch(`/api/v1/footer-links${query}`, {
        headers: { Authorization: `Bearer ${authToken()}` },
      });
      return (await res.json()) as ApiResponse<FooterLink[]>;
    },

    /** Create an external-URL link (admin only). */
    create: async (
      payload: FooterLinkCreatePayload
    ): Promise<ApiResponse<FooterLink>> => {
      const res = await fetch('/api/v1/footer-links', {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify(payload),
      });
      return (await res.json()) as ApiResponse<FooterLink>;
    },

    /** Create a file-backed link by uploading a document (admin only). */
    upload: async (
      file: File,
      titleZh: string,
      titleEn?: string
    ): Promise<ApiResponse<FooterLink>> => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title_zh', titleZh);
      if (titleEn) formData.append('title_en', titleEn);

      const res = await fetch('/api/v1/footer-links/upload-proxy', {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken()}` },
        body: formData,
      });
      return (await res.json()) as ApiResponse<FooterLink>;
    },

    /** Update titles, URL, or visibility (admin only). */
    update: async (
      id: number,
      payload: FooterLinkUpdatePayload
    ): Promise<ApiResponse<FooterLink>> => {
      const res = await fetch(`/api/v1/footer-links/${id}`, {
        method: 'PATCH',
        headers: jsonHeaders(),
        body: JSON.stringify(payload),
      });
      return (await res.json()) as ApiResponse<FooterLink>;
    },

    /** Delete a link and its stored file (admin only). */
    delete: async (
      id: number
    ): Promise<ApiResponse<{ deleted: boolean }>> => {
      const res = await fetch(`/api/v1/footer-links/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${authToken()}` },
      });
      return (await res.json()) as ApiResponse<{ deleted: boolean }>;
    },

    /** Persist a new display order (admin only). */
    reorder: async (
      items: Array<{ id: number; sort_order: number }>
    ): Promise<ApiResponse<{ updated: number }>> => {
      const res = await fetch('/api/v1/footer-links/reorder', {
        method: 'PATCH',
        headers: jsonHeaders(),
        body: JSON.stringify({ items }),
      });
      return (await res.json()) as ApiResponse<{ updated: number }>;
    },
  };
}
