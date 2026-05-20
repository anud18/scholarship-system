/**
 * Tests for `frontend/lib/api/modules/system-settings.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the admin
 * system configuration UI (key/value config, categories,
 * data types, audit logs, public document upload).
 *
 * Wave 6a131 pins URL paths + the SECURITY-relevant
 * include_sensitive query param (admin-controlled visibility
 * of sensitive config like API keys / SMTP passwords) +
 * upload-proxy authentication for admin-only file uploads.
 *
 * 14 cases.
 */

import { createSystemSettingsApi } from "../system-settings";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PUT: jest.fn(),
      DELETE: jest.fn(),
    },
  },
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PUT: jest.Mock;
  DELETE: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createSystemSettingsApi", () => {
  // ─── getConfigurations ─────────────────────────────────────────────

  it("getConfigurations GETs /system-settings with category + include_sensitive filters", async () => {
    // Pin SECURITY: include_sensitive is the admin gate for
    // displaying sensitive config (API keys, SMTP passwords).
    // Pin snake_case so backend Pydantic validates exact key.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createSystemSettingsApi();
    await api.getConfigurations("email", true);
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/system-settings", {
      params: { query: { category: "email", include_sensitive: true } },
    });
  });

  it("getConfigurations omits filters when no args", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createSystemSettingsApi();
    await api.getConfigurations();
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.category).toBeUndefined();
    expect(query.include_sensitive).toBeUndefined();
  });

  // ─── getConfiguration (key is path param) ─────────────────────────

  it("getConfiguration templates key as path id", async () => {
    // Pin: config key (e.g., "smtp_password") goes as PATH
    // param. Pin so refactor to query string doesn't break the
    // backend handler that expects the path template.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createSystemSettingsApi();
    await api.getConfiguration("smtp_password", true);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/system-settings/{id}",
      {
        params: { path: { id: "smtp_password" }, query: { include_sensitive: true } },
      }
    );
  });

  // ─── createConfiguration ───────────────────────────────────────────

  it("createConfiguration POSTs body to /system-settings", async () => {
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createSystemSettingsApi();
    await api.createConfiguration({
      key: "smtp_port",
      value: 587,
      data_type: "integer",
      category: "email",
      description: "SMTP port",
      is_sensitive: false,
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith("/api/v1/system-settings", {
      body: {
        key: "smtp_port",
        value: 587,
        data_type: "integer",
        category: "email",
        description: "SMTP port",
        is_sensitive: false,
      },
    });
  });

  // ─── updateConfiguration ───────────────────────────────────────────

  it("updateConfiguration PUTs /{key} with partial body", async () => {
    // Pin: PUT semantics + partial body (data_type/category
    // are optional). Pin so refactor to PATCH doesn't silently
    // change update contract.
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createSystemSettingsApi();
    await api.updateConfiguration("smtp_port", { value: 465 });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/system-settings/{id}",
      { params: { path: { id: "smtp_port" } }, body: { value: 465 } }
    );
  });

  // ─── validateConfiguration ─────────────────────────────────────────

  it("validateConfiguration POSTs /validate", async () => {
    // Pin: dedicated /validate endpoint — pre-save check that
    // value conforms to data_type. Pin so refactor folding it
    // into create/update would break the admin UI's preview-
    // before-save flow.
    mockedRaw.POST.mockResolvedValueOnce(_ok({ valid: true }));
    const api = createSystemSettingsApi();
    await api.validateConfiguration({
      key: "smtp_port",
      value: 587,
      data_type: "integer",
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/system-settings/validate",
      { body: { key: "smtp_port", value: 587, data_type: "integer" } }
    );
  });

  // ─── deleteConfiguration ───────────────────────────────────────────

  it("deleteConfiguration DELETEs /{key}", async () => {
    mockedRaw.DELETE.mockResolvedValueOnce(_ok({ message: "ok" }));
    const api = createSystemSettingsApi();
    await api.deleteConfiguration("smtp_port");
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/system-settings/{id}",
      { params: { path: { id: "smtp_port" } } }
    );
  });

  // ─── getCategories / getDataTypes (enumeration endpoints) ─────────

  it("getCategories GETs /categories (dynamic enum lookup)", async () => {
    // Pin: dynamic category list — pin so refactor to a static
    // enum doesn't lose backend's runtime-config flexibility.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createSystemSettingsApi();
    await api.getCategories();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/system-settings/categories"
    );
  });

  it("getDataTypes GETs /data-types", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createSystemSettingsApi();
    await api.getDataTypes();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/system-settings/data-types"
    );
  });

  // ─── getAuditLogs ──────────────────────────────────────────────────

  it("getAuditLogs GETs /audit-logs/{config_key} with limit=50 default", async () => {
    // Pin: default limit=50 (admin dashboard page size). Pin so
    // refactor doesn't shrink/grow visible audit history.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createSystemSettingsApi();
    await api.getAuditLogs("smtp_password");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/system-settings/audit-logs/{config_key}",
      { params: { path: { config_key: "smtp_password" }, query: { limit: 50 } } }
    );
  });

  // ─── getPublicDocs (any authenticated user) ────────────────────────

  it("getPublicDocs GETs /public-docs", async () => {
    // Pin: distinct from admin endpoints — any authenticated
    // user can access (NOT just admin). Pin so refactor moving
    // it under /admin/* breaks student-side preview UI.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createSystemSettingsApi();
    await api.getPublicDocs();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/system-settings/public-docs"
    );
  });

  // ─── uploadRegulations / uploadSampleDocument (raw fetch) ─────────

  it("uploadRegulations uses raw fetch to /upload-proxy with key=regulations_url", async () => {
    // Pin: upload uses RAW fetch (not typedClient) due to
    // FormData. Bearer token from localStorage. Pin
    // /upload-proxy?key=regulations_url so refactor doesn't
    // mis-route the upload.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ success: true, data: {} }),
    });
    global.fetch = fetchMock as any;
    Object.defineProperty(global, "localStorage", {
      value: { getItem: () => "test-token" },
      writable: true,
    });

    const api = createSystemSettingsApi();
    await api.uploadRegulations(new File(["x"], "test.pdf"));
    expect(fetchMock).toHaveBeenCalled();
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe(
      "/api/v1/system-settings/upload-proxy?key=regulations_url"
    );
    expect(opts.method).toBe("POST");
    expect(opts.headers.Authorization).toBe("Bearer test-token");
  });

  it("uploadSampleDocument uses key=sample_document_url", async () => {
    // Pin: different key value for sample-doc vs regulations.
    // Pin so refactor doesn't accidentally swap the two upload
    // destinations.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ success: true, data: {} }),
    });
    global.fetch = fetchMock as any;
    Object.defineProperty(global, "localStorage", {
      value: { getItem: () => "test-token" },
      writable: true,
    });

    const api = createSystemSettingsApi();
    await api.uploadSampleDocument(new File(["x"], "sample.pdf"));
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe(
      "/api/v1/system-settings/upload-proxy?key=sample_document_url"
    );
  });

  it("uploadRegulations sends empty Bearer when no token", async () => {
    // Pin: fallback to empty string (not undefined). Backend
    // sees "Bearer " and rejects — pin so refactor doesn't
    // accidentally omit the Authorization header entirely
    // (which would give a different error class).
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({}),
    });
    global.fetch = fetchMock as any;
    Object.defineProperty(global, "localStorage", {
      value: { getItem: () => null },
      writable: true,
    });

    const api = createSystemSettingsApi();
    await api.uploadRegulations(new File(["x"], "x.pdf"));
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.headers.Authorization).toBe("Bearer ");
  });
});
