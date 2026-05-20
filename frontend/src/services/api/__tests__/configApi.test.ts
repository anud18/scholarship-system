/**
 * Tests for `frontend/src/services/api/configApi.ts`.
 *
 * Module had ZERO test coverage. The internal `apiCall` helper handles
 * auth-token attachment + error rejection on non-OK responses. The
 * wrapping methods build URLs from arguments — pinning these prevents
 * silent endpoint drift.
 *
 * Wave 6a109 pins:
 *  - Auth token attached from localStorage when present
 *  - No Authorization header when token absent (anonymous fetch)
 *  - Content-Type: application/json always set
 *  - Non-OK response → throws "API call failed: <statusText>"
 *  - URL construction for each method (path templating)
 *  - Default semester parameter "2025-1" for status endpoints
 *  - PUT body shape for update methods
 *
 * 13 cases.
 */

import { configApi } from "../configApi";

describe("configApi", () => {
  let originalFetch: typeof global.fetch;
  let originalLocalStorage: Storage;

  beforeEach(() => {
    originalFetch = global.fetch;
    originalLocalStorage = global.localStorage;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    Object.defineProperty(global, "localStorage", {
      value: originalLocalStorage,
      writable: true,
    });
  });

  function _mockFetch(response: any, ok = true, statusText = "OK") {
    global.fetch = jest.fn().mockResolvedValue({
      ok,
      statusText,
      json: jest.fn().mockResolvedValue(response),
    }) as any;
  }

  function _mockLocalStorage(token: string | null) {
    const store: Record<string, string> = {};
    if (token) store["auth_token"] = token;
    Object.defineProperty(global, "localStorage", {
      value: {
        getItem: (key: string) => store[key] || null,
        setItem: jest.fn(),
        removeItem: jest.fn(),
        clear: jest.fn(),
        length: 0,
        key: jest.fn(),
      },
      writable: true,
    });
  }

  // ─── Auth token attachment ────────────────────────────────────────

  it("attaches Bearer token from localStorage when present", async () => {
    // Pin: when auth_token is in localStorage, the Authorization
    // header is set. Critical — endpoint will 401 without it.
    _mockFetch({ success: true, message: "", data: [] });
    _mockLocalStorage("test-token-xyz");

    await configApi.getCollegeConfigs();

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[1].headers.Authorization).toBe("Bearer test-token-xyz");
  });

  it("omits Authorization header when no token in localStorage", async () => {
    // Pin: when token absent, NO Authorization header at all (not
    // empty string). Pin so a refactor that always sets the header
    // doesn't accidentally send "Bearer null".
    _mockFetch({ success: true, message: "", data: [] });
    _mockLocalStorage(null);

    await configApi.getCollegeConfigs();

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[1].headers.Authorization).toBeUndefined();
  });

  it("always sets Content-Type: application/json", async () => {
    // Pin: backend expects JSON requests. Header pinned regardless
    // of method.
    _mockFetch({ success: true, message: "", data: [] });
    _mockLocalStorage(null);

    await configApi.getCollegeConfigs();

    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[1].headers["Content-Type"]).toBe("application/json");
  });

  // ─── Error handling ─────────────────────────────────────────────────

  it("throws on non-OK response with statusText in message", async () => {
    // Pin: helper rejects on response.ok=false. The error message
    // includes statusText so callers can surface it. Pin the
    // exact format so log greps stay stable.
    _mockFetch({}, false, "Not Found");
    _mockLocalStorage(null);

    await expect(configApi.getCollegeConfigs()).rejects.toThrow(
      "API call failed: Not Found"
    );
  });

  it("throws even when status text empty", async () => {
    // Pin: non-OK with empty statusText still throws (doesn't
    // silently return).
    _mockFetch({}, false, "");
    _mockLocalStorage(null);

    await expect(configApi.getCollegeConfigs()).rejects.toThrow();
  });

  // ─── URL construction ───────────────────────────────────────────────

  it("getScholarshipTypeConfigs hits /test/types", async () => {
    _mockFetch({ success: true, message: "", data: [] });
    _mockLocalStorage(null);

    await configApi.getScholarshipTypeConfigs();
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/test/types"
    );
  });

  it("getSubTypeConfigs hits /test/sub-types", async () => {
    _mockFetch({ success: true, message: "", data: [] });
    _mockLocalStorage(null);

    await configApi.getSubTypeConfigs();
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/test/sub-types"
    );
  });

  it("getCollegeConfigs hits /test/colleges", async () => {
    _mockFetch({ success: true, message: "", data: [] });
    _mockLocalStorage(null);

    await configApi.getCollegeConfigs();
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/test/colleges"
    );
  });

  it("getRegionConfigs hits /test/regions", async () => {
    _mockFetch({ success: true, message: "", data: [] });
    _mockLocalStorage(null);

    await configApi.getRegionConfigs();
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/test/regions"
    );
  });

  it("getMatrixQuotaStatus templates semester into path", async () => {
    // Pin: semester is templated into URL path, not query string.
    _mockFetch({ success: true, message: "", data: {} });
    _mockLocalStorage(null);

    await configApi.getMatrixQuotaStatus("2024-2");
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/test/matrix-quota-status/2024-2"
    );
  });

  it("getMatrixQuotaStatus uses default semester 2025-1 when omitted", async () => {
    // Pin: default value "2025-1" — pin so a refactor changing the
    // default (e.g., to current semester) is caught.
    _mockFetch({ success: true, message: "", data: {} });
    _mockLocalStorage(null);

    await configApi.getMatrixQuotaStatus();
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/test/matrix-quota-status/2025-1"
    );
  });

  // ─── PUT body shapes ────────────────────────────────────────────────

  it("updateMatrixQuota serializes sub_type/college/new_quota in body", async () => {
    // Pin: backend expects EXACTLY these three snake_case keys.
    // Renaming silently fails backend Pydantic validation.
    _mockFetch({ success: true, message: "", data: {} });
    _mockLocalStorage("token");

    await configApi.updateMatrixQuota("nstc", "A", 10);
    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[1].method).toBe("PUT");
    expect(JSON.parse(fetchCall[1].body)).toEqual({
      sub_type: "nstc",
      college: "A",
      new_quota: 10,
    });
  });

  it("updateRegionalQuota serializes region_code/new_quota in body", async () => {
    _mockFetch({ success: true, message: "", data: {} });
    _mockLocalStorage("token");

    await configApi.updateRegionalQuota("NORTH", 50);
    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[1].method).toBe("PUT");
    expect(JSON.parse(fetchCall[1].body)).toEqual({
      region_code: "NORTH",
      new_quota: 50,
    });
  });

  it("update methods preserve Bearer token", async () => {
    // Pin: PUT requests carry the token. Pin so the auth header
    // logic stays consistent across GET / PUT.
    _mockFetch({ success: true, message: "", data: {} });
    _mockLocalStorage("update-token");

    await configApi.updateRegionalQuota("NORTH", 50);
    const fetchCall = (global.fetch as jest.Mock).mock.calls[0];
    expect(fetchCall[1].headers.Authorization).toBe("Bearer update-token");
  });
});
