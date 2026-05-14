/**
 * Tests for `ExtendedApiClient` ↔ `typedClient` auth-token synchronization.
 *
 * The application has two parallel API clients:
 * - `ApiClient` (legacy, fetch-based) — keeps token in a private field
 *   plus localStorage["auth_token"].
 * - `typedClient` (openapi-fetch based, singleton) — same.
 *
 * Modules use either client depending on era. To keep both in sync,
 * `ExtendedApiClient` overrides `setToken` / `clearToken` to write to
 * both, and overrides `getToken` / `hasToken` to read from `typedClient`
 * (single source of truth on the read path).
 *
 * Regressions in this synchronization cause:
 * - "Phantom logout": user logs in, modules using typedClient still have
 *   no token, requests get 401, login UI bounces.
 * - "Phantom session": user logs out, typedClient cleared but
 *   ExtendedApiClient's super.token still set, modules using legacy
 *   client still send Bearer header → backend sees authenticated user
 *   after they pressed logout (SECURITY).
 *
 * 9 cases. Pure jsdom (jest default).
 */

import { apiClient, ApiClient } from "../index";
import { typedClient } from "../typed-client";

const STORAGE_KEY = "auth_token";

beforeEach(() => {
  localStorage.clear();
  // Drain any state left in either singleton from a prior test.
  apiClient.clearToken();
});

afterAll(() => {
  // Be a polite neighbour — don't leak token state to siblings.
  localStorage.clear();
  apiClient.clearToken();
});

// ─── Construction / inheritance ──────────────────────────────────────

describe("ExtendedApiClient identity", () => {
  it("is an instance of the base ApiClient", () => {
    /* Pin: still extends ApiClient so legacy `instanceof` checks
     * (e.g. type guards in api-error-handler) don't break. */
    expect(apiClient).toBeInstanceOf(ApiClient);
  });
});

// ─── setToken ────────────────────────────────────────────────────────

describe("setToken synchronization", () => {
  it("propagates the token to typedClient", () => {
    /* Pin: setting via the legacy entry-point ALSO populates the
     * openapi-fetch client. Without this, typedClient-backed modules
     * would 401 immediately after login. */
    apiClient.setToken("sync-token-123");

    expect(typedClient.getToken()).toBe("sync-token-123");
    expect(typedClient.hasToken()).toBe(true);
  });

  it("writes the token to localStorage exactly once per call", () => {
    /* Pin: both super.setToken and typedClient.setToken write to the
     * SAME localStorage key. The end state is the same value (not two
     * different keys), so other readers (login UI) see one canonical
     * token. */
    apiClient.setToken("only-token");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("only-token");
  });

  it("overwriting replaces token in both stores", () => {
    apiClient.setToken("first");
    apiClient.setToken("second");

    expect(typedClient.getToken()).toBe("second");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("second");
    // getToken delegates to typedClient (see read-path tests below).
    expect(apiClient.getToken()).toBe("second");
  });
});

// ─── clearToken ──────────────────────────────────────────────────────

describe("clearToken synchronization", () => {
  it("clears the token from typedClient too", () => {
    /* SECURITY: logout MUST clear both clients. Otherwise typedClient
     * keeps sending Bearer header after the user pressed logout. */
    apiClient.setToken("about-to-be-cleared");

    apiClient.clearToken();

    expect(typedClient.hasToken()).toBe(false);
    expect(typedClient.getToken()).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("is idempotent — clearing twice is safe", () => {
    /* Pin: no-op on already-cleared state. Otherwise rapid logout
     * double-click would throw. */
    apiClient.clearToken();
    expect(() => apiClient.clearToken()).not.toThrow();
    expect(apiClient.hasToken()).toBe(false);
  });

  it("clearing without a prior token does not leak any error", () => {
    /* Pin: fresh app boot calls clearToken defensively during session
     * cleanup. Must be safe even when nothing was ever set. */
    expect(() => apiClient.clearToken()).not.toThrow();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

// ─── getToken / hasToken read path ───────────────────────────────────

describe("getToken / hasToken delegate to typedClient", () => {
  it("getToken returns typedClient's current state, not the super class's", () => {
    /* Pin: typedClient is the single source of truth on the read path.
     * If a regression delegated to super.getToken instead, a hot-reload
     * scenario where typedClient was cleared but super still has the
     * token would surface as a phantom session. */
    apiClient.setToken("read-path-token");
    // Mutate typedClient directly to simulate divergence — read should
    // follow typedClient.
    typedClient.clearToken();

    expect(apiClient.getToken()).toBeNull();
    expect(apiClient.hasToken()).toBe(false);
  });

  it("hasToken returns true after setToken, false after clearToken", () => {
    apiClient.setToken("present");
    expect(apiClient.hasToken()).toBe(true);

    apiClient.clearToken();
    expect(apiClient.hasToken()).toBe(false);
  });

  it("hasToken returns false for empty string (boolean coercion)", () => {
    /* Pin: empty string is "no token". Defensive against accidentally
     * storing '' (e.g. from a misconfigured env or stripped JWT). */
    apiClient.setToken("");
    expect(apiClient.hasToken()).toBe(false);
  });
});
