/**
 * Tests for `TypedApiClient` auth-token management.
 *
 * This client is the openapi-fetch based API client (alongside the
 * legacy `ExtendedApiClient`). Auth-token state is mirrored to
 * localStorage so the token survives full-page reloads.
 *
 * Bugs in token handling cause:
 * - User logged out unexpectedly on reload (token not persisted)
 * - Stale token used after logout (clearToken doesn't actually clear)
 * - Token stored under wrong localStorage key → other code that reads
 *   the auth_token key (login UI, error overlay) is out of sync
 *
 * 8 cases. Pure DOM via jsdom (jest default).
 */

import { TypedApiClient } from "../typed-client";

const STORAGE_KEY = "auth_token";

beforeEach(() => {
  // Fresh localStorage between tests
  localStorage.clear();
});

// ─── Construction + initial token state ──────────────────────────────

describe("TypedApiClient construction", () => {
  it("starts with no token when localStorage is empty", () => {
    const client = new TypedApiClient();
    expect(client.hasToken()).toBe(false);
    expect(client.getToken()).toBeNull();
  });

  it("hydrates token from localStorage on construction", () => {
    /* Pin: token persists across page reloads via localStorage.
     * A regression that doesn't read on construct would log the user
     * out on every reload. */
    localStorage.setItem(STORAGE_KEY, "stored-token-abc");
    const client = new TypedApiClient();
    expect(client.hasToken()).toBe(true);
    expect(client.getToken()).toBe("stored-token-abc");
  });
});

// ─── setToken ────────────────────────────────────────────────────────

describe("setToken", () => {
  it("stores token in instance AND localStorage", () => {
    /* Pin: BOTH stores updated. Otherwise reload would lose state OR
     * other code reading localStorage directly would see stale value. */
    const client = new TypedApiClient();
    client.setToken("new-token-xyz");

    expect(client.getToken()).toBe("new-token-xyz");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("new-token-xyz");
  });

  it("overwrites a previously-set token", () => {
    const client = new TypedApiClient();
    client.setToken("old");
    client.setToken("new");

    expect(client.getToken()).toBe("new");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("new");
  });
});

// ─── clearToken ──────────────────────────────────────────────────────

describe("clearToken", () => {
  it("removes token from instance AND localStorage", () => {
    /* SECURITY: clearToken must fully purge. If localStorage still has
     * the token, a refresh would log the user back in despite "logout". */
    const client = new TypedApiClient();
    client.setToken("session-token");

    client.clearToken();

    expect(client.hasToken()).toBe(false);
    expect(client.getToken()).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("is idempotent — clearing twice is safe", () => {
    /* Pin: no-op on already-cleared state. Otherwise rapid double-click
     * on logout button could throw. */
    const client = new TypedApiClient();
    client.clearToken();
    client.clearToken();
    expect(client.hasToken()).toBe(false);
  });

  it("clearing one client instance affects localStorage but not other instances", () => {
    /* Pin: each instance has its own in-memory `token` field, but
     * localStorage is shared. After clearToken on client1, client2's
     * in-memory token is stale (not auto-cleared). This is intentional
     * — caller is responsible for syncing.
     *
     * Pin so the surprise is documented. */
    const client1 = new TypedApiClient();
    const client2 = new TypedApiClient();
    client1.setToken("shared-token");

    // client2 was constructed earlier with empty localStorage so its
    // in-memory token is still null. Set it manually now.
    client2.setToken("shared-token");

    client1.clearToken();

    // localStorage cleared
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    // client1 fully cleared
    expect(client1.hasToken()).toBe(false);
    // client2 still has token in memory (separate instance)
    expect(client2.getToken()).toBe("shared-token");
  });
});

// ─── hasToken / getToken ─────────────────────────────────────────────

describe("hasToken / getToken", () => {
  it("hasToken returns boolean, getToken returns the raw value", () => {
    /* Pin: hasToken is a boolean shortcut for the common 'are we
     * logged in' check. A regression returning the token string from
     * hasToken would still be truthy but break type-checking callers. */
    const client = new TypedApiClient();
    client.setToken("xyz");

    expect(typeof client.hasToken()).toBe("boolean");
    expect(client.hasToken()).toBe(true);
    expect(client.getToken()).toBe("xyz");
  });

  it("hasToken returns false for empty string token", () => {
    /* Pin: empty string is treated as 'no token' (uses !! coercion).
     * Defensive against accidentally storing '' as the token. */
    const client = new TypedApiClient();
    client.setToken("");
    expect(client.hasToken()).toBe(false);
  });
});
