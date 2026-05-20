/**
 * Tests for `frontend/lib/api/client.ts` — ApiClient token state
 * management + content-type/body-reader defensive helpers.
 *
 * client.ts has typed-client.test.ts + compat.test.ts + modular-
 * api.test.ts but ZERO dedicated tests for the base ApiClient
 * class's token state + defensive helpers. SECURITY-critical:
 * Bearer token lifecycle drives every authenticated request.
 *
 * Wave 6a149 pins setToken/clearToken/hasToken/getToken state,
 * localStorage persistence + retrieval, and the defensive
 * helpers that tolerate non-standard fetch responses (e.g.
 * test mocks, React Native whatwg-fetch polyfill).
 *
 * `request()` itself requires network mocking — not in scope.
 */

import { ApiClient } from "../client";

beforeEach(() => {
  // Reset localStorage between tests for state isolation
  if (typeof window !== "undefined" && window.localStorage) {
    window.localStorage.clear();
  }
});

describe("ApiClient token state", () => {
  it("starts with null token when localStorage empty", () => {
    // Pin: fresh instance with no stored token → token=null.
    const client = new ApiClient();
    expect(client.hasToken()).toBe(false);
    expect(client.getToken()).toBeNull();
  });

  it("setToken persists to localStorage AND updates in-memory", () => {
    // Pin SECURITY: setToken writes to both in-memory state
    // (this.token) AND localStorage. Pin so refactor doesn't
    // skip persistence (would lose token on page reload).
    const client = new ApiClient();
    client.setToken("test-jwt-token");
    expect(client.hasToken()).toBe(true);
    expect(client.getToken()).toBe("test-jwt-token");
    expect(window.localStorage.getItem("auth_token")).toBe("test-jwt-token");
  });

  it("clearToken removes from BOTH in-memory and localStorage", () => {
    // Pin SECURITY: clearToken wipes both. Pin so logout
    // doesn't leak the token via localStorage to the next
    // session.
    const client = new ApiClient();
    client.setToken("test-jwt-token");
    client.clearToken();
    expect(client.hasToken()).toBe(false);
    expect(client.getToken()).toBeNull();
    expect(window.localStorage.getItem("auth_token")).toBeNull();
  });

  it("new instance reads existing token from localStorage", () => {
    // Pin: constructor reads localStorage.auth_token. Pin so
    // page reload restores authenticated state automatically.
    window.localStorage.setItem("auth_token", "persisted-token");
    const client = new ApiClient();
    expect(client.hasToken()).toBe(true);
    expect(client.getToken()).toBe("persisted-token");
  });

  it("hasToken returns boolean (NOT the token value)", () => {
    // Pin: hasToken returns boolean only — refactor returning
    // truthy/falsy unwrapped would leak the token via type
    // coercion at call sites.
    const client = new ApiClient();
    expect(typeof client.hasToken()).toBe("boolean");
    client.setToken("x");
    expect(typeof client.hasToken()).toBe("boolean");
  });

  it("getToken returns null (not undefined) when unset", () => {
    // Pin: getToken returns explicit null (NOT undefined).
    // Pin so callers using `=== null` checks stay correct.
    const client = new ApiClient();
    expect(client.getToken()).toBeNull();
    expect(client.getToken()).not.toBeUndefined();
  });

  it("setToken with empty string is treated as falsy by hasToken", () => {
    // Pin DOCUMENTED-BEHAVIOR: setToken("") stores empty string;
    // hasToken returns false (uses !! truthy check). Pin so
    // refactor doesn't accidentally allow empty-Bearer
    // requests.
    const client = new ApiClient();
    client.setToken("");
    expect(client.hasToken()).toBe(false);
    expect(client.getToken()).toBe("");
  });
});

describe("ApiClient defensive helpers", () => {
  // Access private methods via cast for testing. These are
  // SECURITY-critical defensive paths that tolerate non-standard
  // fetch implementations (React Native polyfills, jest mocks).

  it("getContentType handles real Headers instance", () => {
    const client = new ApiClient();
    const realHeaders = new Headers({ "content-type": "application/json" });
    const ct = (client as any).getContentType({ headers: realHeaders });
    expect(ct).toBe("application/json");
  });

  it("getContentType handles plain object headers (test mock shape)", () => {
    // Pin: when headers is a plain {} (e.g. jest mock),
    // fall back to dictionary lookup. Pin so test mocks
    // don't need to use full Headers instances.
    const client = new ApiClient();
    const ct = (client as any).getContentType({
      headers: { "content-type": "text/html" },
    });
    expect(ct).toBe("text/html");
  });

  it("getContentType handles case-variant Content-Type header keys", () => {
    // Pin: tolerates 3 case variants (content-type / Content-Type
    // / Content-type). HTTP headers are case-insensitive but
    // jest mocks may use any case.
    const client = new ApiClient();
    expect(
      (client as any).getContentType({ headers: { "Content-Type": "x/a" } })
    ).toBe("x/a");
    expect(
      (client as any).getContentType({ headers: { "Content-type": "x/b" } })
    ).toBe("x/b");
  });

  it("getContentType returns empty string when no headers", () => {
    // Pin: missing headers → "" (NOT undefined or null). Pin
    // so caller's string checks (e.g. .startsWith) don't crash.
    const client = new ApiClient();
    expect((client as any).getContentType({})).toBe("");
    expect((client as any).getContentType({ headers: undefined })).toBe("");
  });

  it("getContentType returns empty string when headers is non-object", () => {
    const client = new ApiClient();
    expect((client as any).getContentType({ headers: null })).toBe("");
  });

  it("readTextSafe prefers .text() when available", async () => {
    const client = new ApiClient();
    const result = await (client as any).readTextSafe({
      text: () => Promise.resolve("hello world"),
    });
    expect(result).toBe("hello world");
  });

  it("readTextSafe falls back to JSON.stringify(.json()) when text() throws", async () => {
    // Pin: when .text() throws (e.g. body already consumed),
    // fall back to .json() and JSON.stringify the result.
    // Pin so test mocks that only implement .json() still
    // work.
    const client = new ApiClient();
    const result = await (client as any).readTextSafe({
      text: () => {
        throw new Error("body locked");
      },
      json: () => Promise.resolve({ ok: true }),
    });
    expect(result).toBe('{"ok":true}');
  });

  it("readTextSafe falls back to .body when string", async () => {
    // Pin: when .text() and .json() missing, fall back to
    // string body. Pin defensive handling for unusual mocks.
    const client = new ApiClient();
    const result = await (client as any).readTextSafe({
      body: "plain string body",
    });
    expect(result).toBe("plain string body");
  });

  it("readTextSafe falls back to React-Native _bodyInit polyfill field", async () => {
    // Pin: React Native's whatwg-fetch polyfill exposes
    // `_bodyInit` instead of working text(). Pin so RN mobile
    // clients aren't accidentally broken by refactor that drops
    // this specific fallback.
    const client = new ApiClient();
    const result = await (client as any).readTextSafe({
      _bodyInit: "rn-polyfill-body",
    });
    expect(result).toBe("rn-polyfill-body");
  });

  it("readTextSafe returns empty string when no body extractor works", async () => {
    // Pin: completely-empty response object → "" (NOT throw,
    // NOT undefined). Pin so caller's downstream parsing
    // doesn't crash.
    const client = new ApiClient();
    const result = await (client as any).readTextSafe({});
    expect(result).toBe("");
  });
});

describe("ApiValidationError class", () => {
  it("preserves zodError, endpoint, responseData on instance", async () => {
    // Pin: ApiValidationError exposes 4 properties for
    // downstream error handling. Pin so logger/Sentry can
    // serialize them.
    const { ApiValidationError } = await import("../client");
    const { z } = await import("zod");

    let zodErr: any;
    try {
      z.string().parse(123);
    } catch (e) {
      zodErr = e;
    }
    const err = new ApiValidationError(
      "test-message",
      zodErr,
      "/api/v1/x",
      { bad: "data" }
    );
    expect(err.message).toBe("test-message");
    expect(err.name).toBe("ApiValidationError");
    expect(err.zodError).toBe(zodErr);
    expect(err.endpoint).toBe("/api/v1/x");
    expect(err.responseData).toEqual({ bad: "data" });
  });

  it("is an instance of Error (catch (e) { e instanceof Error }) works", async () => {
    const { ApiValidationError } = await import("../client");
    const err = new ApiValidationError(
      "x",
      {} as any,
      "/api/v1/x",
      null
    );
    expect(err).toBeInstanceOf(Error);
  });
});
