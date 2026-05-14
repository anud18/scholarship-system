/**
 * Tests for the base `ApiClient` token-management methods.
 *
 * Wave 6a46 covered `TypedApiClient` (the openapi-fetch sibling).
 * Wave 6a58 covered `ExtendedApiClient` ↔ `typedClient` synchronization.
 * This wave pins the base `ApiClient`'s standalone token methods +
 * localStorage hydration on construction.
 *
 * The base class is used directly by some legacy callers; if its
 * token methods drift from TypedApiClient's behaviour, login state
 * becomes inconsistent between modules.
 *
 * 11 cases. Pure jsdom (jest default).
 */

import { ApiClient } from "../client";

const STORAGE_KEY = "auth_token";

beforeEach(() => {
  localStorage.clear();
});

// ─── Construction + initial hydration ────────────────────────────────

describe("ApiClient construction", () => {
  it("starts with no token when localStorage is empty", () => {
    const client = new ApiClient();
    expect(client.hasToken()).toBe(false);
    expect(client.getToken()).toBeNull();
  });

  it("hydrates token from localStorage on construction", () => {
    /* Pin: persisted token survives full-page reload. Without this,
     * users would be logged out on every browser refresh. */
    localStorage.setItem(STORAGE_KEY, "persisted-token");
    const client = new ApiClient();
    expect(client.hasToken()).toBe(true);
    expect(client.getToken()).toBe("persisted-token");
  });
});

// ─── setToken ────────────────────────────────────────────────────────

describe("setToken", () => {
  it("stores token in both instance and localStorage", () => {
    /* Pin: dual-write. localStorage persists; instance field is the
     * cached read path for hasToken/getToken. */
    const client = new ApiClient();
    client.setToken("new-token");

    expect(client.getToken()).toBe("new-token");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("new-token");
  });

  it("overwrites previously-set token", () => {
    const client = new ApiClient();
    client.setToken("first");
    client.setToken("second");

    expect(client.getToken()).toBe("second");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("second");
  });
});

// ─── clearToken ──────────────────────────────────────────────────────

describe("clearToken", () => {
  it("removes token from both instance and localStorage", () => {
    /* SECURITY: logout must clear both stores. Otherwise a refresh
     * would re-authenticate the user despite "logout". */
    const client = new ApiClient();
    client.setToken("session-token");

    client.clearToken();

    expect(client.hasToken()).toBe(false);
    expect(client.getToken()).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("is idempotent — safe to call twice", () => {
    const client = new ApiClient();
    client.clearToken();
    expect(() => client.clearToken()).not.toThrow();
    expect(client.hasToken()).toBe(false);
  });

  it("safe to call when no prior token exists", () => {
    /* Pin: fresh app boot calls clearToken() defensively during
     * session cleanup. Must not throw on empty state. */
    const client = new ApiClient();
    expect(() => client.clearToken()).not.toThrow();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

// ─── hasToken / getToken ─────────────────────────────────────────────

describe("hasToken / getToken contract", () => {
  it("hasToken returns boolean true/false (not the raw token string)", () => {
    /* Pin: hasToken returns boolean. Returning the token string from
     * hasToken would still be truthy but break TS callers expecting
     * `boolean`. */
    const client = new ApiClient();
    client.setToken("xyz");
    expect(typeof client.hasToken()).toBe("boolean");
    expect(client.hasToken()).toBe(true);

    client.clearToken();
    expect(typeof client.hasToken()).toBe("boolean");
    expect(client.hasToken()).toBe(false);
  });

  it("hasToken returns false for empty string token (boolean coercion)", () => {
    /* Pin: empty string is treated as "no token" (uses !!).
     * Defensive against accidentally storing '' from a misconfigured
     * env or stripped JWT. */
    const client = new ApiClient();
    client.setToken("");
    expect(client.hasToken()).toBe(false);
  });

  it("getToken returns null (not undefined) when no token set", () => {
    /* Pin: null is the documented "no token" sentinel — TypeScript
     * `string | null` callers depend on it. */
    const client = new ApiClient();
    expect(client.getToken()).toBeNull();
  });
});

// ─── Multi-instance isolation ────────────────────────────────────────

describe("multi-instance behaviour", () => {
  it("each instance has its own in-memory token field", () => {
    /* Pin: in-memory state is per-instance, but localStorage is
     * shared. After setToken on c1, c2's in-memory field is still
     * the value it hydrated on construction (or null). */
    const c1 = new ApiClient();
    const c2 = new ApiClient();

    c1.setToken("c1-only");

    // localStorage shared
    expect(localStorage.getItem(STORAGE_KEY)).toBe("c1-only");
    expect(c1.getToken()).toBe("c1-only");
    // c2 was constructed before c1's setToken — its cached field is
    // still null (it doesn't auto-rehydrate)
    expect(c2.getToken()).toBeNull();
  });

  it("clearing one instance clears localStorage for all", () => {
    const c1 = new ApiClient();
    const c2 = new ApiClient();
    c1.setToken("shared");
    c2.setToken("shared"); // refresh c2's cached field

    c1.clearToken();

    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(c1.hasToken()).toBe(false);
    // c2's in-memory field NOT auto-cleared; documented behavior.
    expect(c2.getToken()).toBe("shared");
  });
});
