/**
 * Tests for `frontend/src/services/api/scholarshipConfigApi.ts`.
 *
 * Module had ZERO test coverage. Drives the admin scholarship
 * configuration UI — every CRUD method here is on the critical
 * path for editing scholarship rules.
 *
 * Wave 6a110 pins:
 *  - Query-string construction with conditional filters
 *  - Path-templating for /{id} endpoints
 *  - POST/PUT/DELETE method dispatch + body shapes
 *  - cloneConfiguration body uses {config_name} key
 *  - exportQualifiedApplicants: format param (default "csv"),
 *    optional semester, Authorization header, csv→text() /
 *    excel→blob() branching
 *  - Non-OK export response throws "Export failed: ..."
 *
 * 18 cases.
 */

import { scholarshipConfigApi } from "../scholarshipConfigApi";

describe("scholarshipConfigApi", () => {
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

  function _mockFetch(opts: {
    body?: any;
    text?: string;
    blob?: Blob;
    ok?: boolean;
    statusText?: string;
  }) {
    const { body, text, blob, ok = true, statusText = "OK" } = opts;
    global.fetch = jest.fn().mockResolvedValue({
      ok,
      statusText,
      json: jest.fn().mockResolvedValue(body ?? {}),
      text: jest.fn().mockResolvedValue(text ?? ""),
      blob: jest.fn().mockResolvedValue(blob ?? new Blob()),
    }) as any;
  }

  function _mockLocalStorage(token: string | null) {
    const store: Record<string, string> = {};
    if (token) store["auth_token"] = token;
    Object.defineProperty(global, "localStorage", {
      value: {
        getItem: (k: string) => store[k] || null,
        setItem: jest.fn(),
        removeItem: jest.fn(),
        clear: jest.fn(),
        length: 0,
        key: jest.fn(),
      },
      writable: true,
    });
  }

  // ─── getConfigurations query params ────────────────────────────────

  it("getConfigurations builds no query string when no params", async () => {
    _mockFetch({ body: { success: true, data: [] } });
    _mockLocalStorage(null);

    await scholarshipConfigApi.getConfigurations();
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations"
    );
  });

  it("getConfigurations builds query string with single param", async () => {
    _mockFetch({ body: { success: true, data: [] } });
    _mockLocalStorage(null);

    await scholarshipConfigApi.getConfigurations({ scholarship_type_id: 5 });
    const url = (global.fetch as jest.Mock).mock.calls[0][0];
    expect(url).toBe(
      "/api/v1/scholarship-configurations?scholarship_type_id=5"
    );
  });

  it("getConfigurations builds query string with all 3 params", async () => {
    _mockFetch({ body: { success: true, data: [] } });
    _mockLocalStorage(null);

    await scholarshipConfigApi.getConfigurations({
      scholarship_type_id: 1,
      category: "phd",
      is_active: true,
    });
    const url = (global.fetch as jest.Mock).mock.calls[0][0];
    expect(url).toContain("scholarship_type_id=1");
    expect(url).toContain("category=phd");
    expect(url).toContain("is_active=true");
  });

  it("getConfigurations includes is_active=false (not omitted)", async () => {
    // Pin: explicit false is included via `!== undefined` check —
    // pin so a refactor to `if (is_active)` doesn't silently drop
    // the false-filter (which would return active+inactive instead
    // of only inactive).
    _mockFetch({ body: { success: true, data: [] } });
    _mockLocalStorage(null);

    await scholarshipConfigApi.getConfigurations({ is_active: false });
    const url = (global.fetch as jest.Mock).mock.calls[0][0];
    expect(url).toContain("is_active=false");
  });

  // ─── Path templating ───────────────────────────────────────────────

  it("getConfiguration templates id into path", async () => {
    _mockFetch({ body: { success: true, data: {} } });
    _mockLocalStorage(null);

    await scholarshipConfigApi.getConfiguration(42);
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/42"
    );
  });

  it("getScholarshipTypesWithConfigs hits documented sub-route", async () => {
    _mockFetch({ body: { success: true, data: [] } });
    _mockLocalStorage(null);

    await scholarshipConfigApi.getScholarshipTypesWithConfigs();
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/types-with-configs"
    );
  });

  it("getQuotaStatus omits semester query when undefined", async () => {
    _mockFetch({ body: { success: true, data: {} } });
    _mockLocalStorage(null);

    await scholarshipConfigApi.getQuotaStatus(7);
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/7/quota-status"
    );
  });

  it("getQuotaStatus appends semester query when provided", async () => {
    _mockFetch({ body: { success: true, data: {} } });
    _mockLocalStorage(null);

    await scholarshipConfigApi.getQuotaStatus(7, "2024-2");
    expect((global.fetch as jest.Mock).mock.calls[0][0]).toBe(
      "/api/v1/scholarship-configurations/7/quota-status?semester=2024-2"
    );
  });

  // ─── CRUD methods ───────────────────────────────────────────────────

  it("createConfiguration POSTs body JSON", async () => {
    _mockFetch({ body: { success: true, data: {} } });
    _mockLocalStorage("admin-token");

    await scholarshipConfigApi.createConfiguration({ config_name: "test" });
    const call = (global.fetch as jest.Mock).mock.calls[0];
    expect(call[0]).toBe("/api/v1/scholarship-configurations");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ config_name: "test" });
  });

  it("updateConfiguration PUTs to /{id} with body", async () => {
    _mockFetch({ body: { success: true, data: {} } });
    _mockLocalStorage("admin-token");

    await scholarshipConfigApi.updateConfiguration(99, { is_active: false });
    const call = (global.fetch as jest.Mock).mock.calls[0];
    expect(call[0]).toBe("/api/v1/scholarship-configurations/99");
    expect(call[1].method).toBe("PUT");
    expect(JSON.parse(call[1].body)).toEqual({ is_active: false });
  });

  it("deleteConfiguration DELETEs /{id} with no body", async () => {
    _mockFetch({ body: { success: true, data: null } });
    _mockLocalStorage("admin-token");

    await scholarshipConfigApi.deleteConfiguration(99);
    const call = (global.fetch as jest.Mock).mock.calls[0];
    expect(call[0]).toBe("/api/v1/scholarship-configurations/99");
    expect(call[1].method).toBe("DELETE");
    expect(call[1].body).toBeUndefined();
  });

  it("cloneConfiguration POSTs /{id}/clone with config_name key", async () => {
    // Pin: body uses {config_name} (NOT {name} or {new_name}).
    // Backend Pydantic validates this exact key.
    _mockFetch({ body: { success: true, data: {} } });
    _mockLocalStorage("admin-token");

    await scholarshipConfigApi.cloneConfiguration(7, "Clone of A");
    const call = (global.fetch as jest.Mock).mock.calls[0];
    expect(call[0]).toBe("/api/v1/scholarship-configurations/7/clone");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ config_name: "Clone of A" });
  });

  it("validateConfiguration POSTs to /validate", async () => {
    _mockFetch({
      body: { success: true, data: { is_valid: true, errors: [] } },
    });
    _mockLocalStorage("admin-token");

    await scholarshipConfigApi.validateConfiguration({ config_name: "x" });
    const call = (global.fetch as jest.Mock).mock.calls[0];
    expect(call[0]).toBe("/api/v1/scholarship-configurations/validate");
    expect(call[1].method).toBe("POST");
  });

  // ─── exportQualifiedApplicants ──────────────────────────────────────

  it("exportQualifiedApplicants defaults format to csv", async () => {
    // Pin: default format is "csv". The function returns
    // { data: text } shape (not blob) when format is csv.
    _mockFetch({ text: "header1,header2\nval1,val2" });
    _mockLocalStorage("admin-token");

    const out = await scholarshipConfigApi.exportQualifiedApplicants(42);
    const url = (global.fetch as jest.Mock).mock.calls[0][0];
    expect(url).toContain("format=csv");
    expect(out).toEqual({ data: "header1,header2\nval1,val2" });
  });

  it("exportQualifiedApplicants format=excel returns blob", async () => {
    // Pin: format=excel branch returns Blob (not { data: ... }).
    // Two distinct return shapes — callers branch on format.
    const fakeBlob = new Blob(["xlsx-content"]);
    _mockFetch({ blob: fakeBlob });
    _mockLocalStorage("admin-token");

    const out = await scholarshipConfigApi.exportQualifiedApplicants(
      42,
      undefined,
      "excel"
    );
    expect(out).toBe(fakeBlob);
  });

  it("exportQualifiedApplicants appends optional semester", async () => {
    _mockFetch({ text: "x" });
    _mockLocalStorage("admin-token");

    await scholarshipConfigApi.exportQualifiedApplicants(42, "2024-2");
    const url = (global.fetch as jest.Mock).mock.calls[0][0];
    expect(url).toContain("semester=2024-2");
  });

  it("exportQualifiedApplicants attaches Bearer token", async () => {
    _mockFetch({ text: "x" });
    _mockLocalStorage("export-token");

    await scholarshipConfigApi.exportQualifiedApplicants(42);
    const headers = (global.fetch as jest.Mock).mock.calls[0][1].headers;
    expect(headers.Authorization).toBe("Bearer export-token");
  });

  it("exportQualifiedApplicants omits Authorization when no token", async () => {
    _mockFetch({ text: "x" });
    _mockLocalStorage(null);

    await scholarshipConfigApi.exportQualifiedApplicants(42);
    const headers = (global.fetch as jest.Mock).mock.calls[0][1].headers;
    expect(headers.Authorization).toBeUndefined();
  });

  it("exportQualifiedApplicants throws on non-OK with statusText", async () => {
    // Pin: exact error format "Export failed: <statusText>".
    _mockFetch({ ok: false, statusText: "Forbidden" });
    _mockLocalStorage("token");

    await expect(
      scholarshipConfigApi.exportQualifiedApplicants(42)
    ).rejects.toThrow("Export failed: Forbidden");
  });
});
