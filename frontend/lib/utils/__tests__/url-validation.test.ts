/**
 * SECURITY tests for `frontend/lib/utils/url-validation.ts`.
 *
 * These helpers are the application's first line of defence against
 * **open-redirect** vulnerabilities (CWE-601). A regression here lets an
 * attacker control where the user lands after login or after clicking a
 * "preview document" link — classic phishing setup, abused in OAuth /
 * SSO flows in particular.
 *
 * Functions under test:
 * - `validateSameOriginUrl(path)` — only same-origin relative paths pass.
 * - `buildSecurePreviewUrl(endpoint, params)` — allowlist + URL API
 *   construction; final result must still pass same-origin check.
 * - `getAuthToken()` — token retrieval fallback chain.
 *
 * A single bypass (e.g. accepting `//evil.com/x` because `startsWith('/')`
 * is true) would be catastrophic for phishing exposure, so every escape
 * pattern is pinned.
 *
 * 23 cases. Pure jsdom (jest default).
 */

import {
  buildSecurePreviewUrl,
  getAuthToken,
  validateSameOriginUrl,
} from "../url-validation";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

// ─── validateSameOriginUrl ───────────────────────────────────────────

describe("validateSameOriginUrl", () => {
  it("accepts a simple relative path", () => {
    expect(validateSameOriginUrl("/dashboard")).toBe("/dashboard");
  });

  it("preserves the search component", () => {
    /* Pin: ?query=string is part of the legitimate URL and must survive.
     * Used by buildSecurePreviewUrl for token=... etc. */
    expect(validateSameOriginUrl("/preview?token=abc&id=42")).toBe(
      "/preview?token=abc&id=42"
    );
  });

  it("strips any origin from the returned value", () => {
    /* Pin: returns pathname + search ONLY, never the origin. Callers can
     * concatenate to a known-safe base without worrying about double
     * origins. */
    const out = validateSameOriginUrl("/x/y?z=1");
    expect(out.startsWith("http")).toBe(false);
    expect(out.startsWith("//")).toBe(false);
  });

  it("rejects protocol-relative URLs (//evil.com)", () => {
    /* SECURITY: `//evil.com/x` is the classic open-redirect bypass. It
     * does NOT start with `/` from the URL-parser's POV (it's
     * protocol-relative), so `new URL('//x', origin)` would change
     * origin. The startsWith('/') check is true for "//" — the
     * origin-equality check is what actually blocks the attack. Pin
     * both layers. */
    expect(() => validateSameOriginUrl("//evil.com/path")).toThrow(
      /Cross-origin/
    );
  });

  it("rejects absolute URLs to a different origin", () => {
    expect(() => validateSameOriginUrl("https://evil.com/x")).toThrow(
      /Only relative URLs/
    );
  });

  it("rejects http://localhost:8000 even if it 'looks local'", () => {
    /* Pin: absolute URLs are absolute. Don't special-case localhost. */
    expect(() => validateSameOriginUrl("http://localhost:8000/x")).toThrow(
      /Only relative URLs/
    );
  });

  it("rejects a bare path without leading slash", () => {
    /* Pin: `dashboard` (no leading `/`) would resolve relative to the
     * current document URL — surprising for callers. Force explicit
     * absolute-relative form. */
    expect(() => validateSameOriginUrl("dashboard")).toThrow(
      /Only relative URLs/
    );
  });

  it("rejects empty string", () => {
    expect(() => validateSameOriginUrl("")).toThrow();
  });

  it("rejects javascript: pseudo-protocol", () => {
    /* SECURITY: `javascript:alert(1)` doesn't start with `/` so the
     * first check rejects it. Pin so a future refactor can't lose this
     * by accident. */
    expect(() => validateSameOriginUrl("javascript:alert(1)")).toThrow(
      /Only relative URLs/
    );
  });

  it("rejects data: pseudo-protocol", () => {
    /* SECURITY: data:text/html,<script>... XSS sink. */
    expect(() => validateSameOriginUrl("data:text/html,<x>")).toThrow(
      /Only relative URLs/
    );
  });

  it("preserves URL-encoded characters in pathname", () => {
    /* Pin: percent-encoded paths survive the round-trip via the URL
     * API. Important for filenames with spaces / unicode in our
     * preview URLs. */
    const out = validateSameOriginUrl("/files/My%20Doc.pdf");
    expect(out).toContain("My%20Doc.pdf");
  });
});

// ─── buildSecurePreviewUrl ───────────────────────────────────────────

describe("buildSecurePreviewUrl", () => {
  it("constructs a preview URL with query parameters", () => {
    const url = buildSecurePreviewUrl("/api/v1/preview", {
      token: "abc",
      app_id: 42,
    });
    expect(url.startsWith("/api/v1/preview?")).toBe(true);
    expect(url).toContain("token=abc");
    expect(url).toContain("app_id=42");
  });

  it("rejects endpoints not in the allowlist", () => {
    /* SECURITY: allowlist is the wall. Anyone passing a user-controlled
     * endpoint must hit this barrier. */
    expect(() =>
      buildSecurePreviewUrl("/api/v1/admin/users", { id: 1 })
    ).toThrow(/not in allowlist/);
  });

  it("rejects an arbitrary attacker-controlled endpoint", () => {
    expect(() =>
      buildSecurePreviewUrl("https://evil.com/preview", {})
    ).toThrow(/not in allowlist/);
  });

  it("accepts all three allowlisted endpoints", () => {
    /* Pin: pin the exact allowlist so anyone widening it has to update
     * this test (forcing review). */
    expect(buildSecurePreviewUrl("/api/v1/preview", {})).toBe(
      "/api/v1/preview"
    );
    expect(
      buildSecurePreviewUrl("/api/v1/preview/examples", {})
    ).toBe("/api/v1/preview/examples");
    expect(buildSecurePreviewUrl("/api/v1/download", {})).toBe(
      "/api/v1/download"
    );
  });

  it("omits undefined params from the query string", () => {
    /* Pin: don't serialise `key=undefined` literally. Important for
     * optional query params. */
    const url = buildSecurePreviewUrl("/api/v1/preview", {
      token: "x",
      missing: undefined,
    });
    expect(url).toContain("token=x");
    expect(url).not.toContain("missing");
  });

  it("URL-encodes special characters in param values", () => {
    /* Pin: URLSearchParams must do the encoding. A regression that
     * used string concat would expose XSS / param-injection. */
    const url = buildSecurePreviewUrl("/api/v1/preview", {
      filename: "a b&c=d",
    });
    expect(url).toContain("filename=a+b%26c%3Dd");
  });

  it("returns a same-origin path (no protocol or host)", () => {
    const url = buildSecurePreviewUrl("/api/v1/preview", { x: 1 });
    expect(url.startsWith("http")).toBe(false);
    expect(url.startsWith("//")).toBe(false);
  });

  it("coerces numeric params to strings", () => {
    /* Pin: ID-like params often pass through as `number`. */
    const url = buildSecurePreviewUrl("/api/v1/download", { app_id: 12345 });
    expect(url).toContain("app_id=12345");
  });
});

// ─── getAuthToken ────────────────────────────────────────────────────

describe("getAuthToken", () => {
  it("returns empty string when no token is anywhere", () => {
    /* Pin: empty string sentinel, not null/undefined. Callers append
     * directly to query strings. */
    expect(getAuthToken()).toBe("");
  });

  it("reads from localStorage 'auth_token' first", () => {
    /* Pin: lookup order matters — this is the canonical key used by
     * the rest of the app. */
    localStorage.setItem("auth_token", "primary");
    localStorage.setItem("token", "secondary");
    sessionStorage.setItem("auth_token", "tertiary");

    expect(getAuthToken()).toBe("primary");
  });

  it("falls back to localStorage 'token' when 'auth_token' is missing", () => {
    /* Pin: legacy key compatibility — older code paths still write
     * 'token'. */
    localStorage.setItem("token", "legacy");
    expect(getAuthToken()).toBe("legacy");
  });

  it("falls back to sessionStorage when localStorage is empty", () => {
    sessionStorage.setItem("auth_token", "session-tok");
    expect(getAuthToken()).toBe("session-tok");
  });

  it("returns empty string when all four locations are empty strings", () => {
    /* Pin: empty string in storage should propagate as empty (not
     * stringify to 'undefined' or throw). Tests the `||` chain
     * short-circuits correctly. */
    localStorage.setItem("auth_token", "");
    localStorage.setItem("token", "");
    sessionStorage.setItem("auth_token", "");
    sessionStorage.setItem("token", "");

    expect(getAuthToken()).toBe("");
  });

  it("does not mutate storage as a side effect", () => {
    /* Pin: pure read. A regression that wrote-back the resolved token
     * would clobber the canonical key on every call. */
    sessionStorage.setItem("auth_token", "from-session");
    getAuthToken();
    expect(localStorage.getItem("auth_token")).toBeNull();
    expect(sessionStorage.getItem("auth_token")).toBe("from-session");
  });
});
