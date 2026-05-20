/**
 * Tests for `frontend/lib/api/modules/application-fields.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the admin
 * dynamic-form-builder UI (per-scholarship field/document
 * configuration).
 *
 * Wave 6a124 pins URL paths + path templating + verb dispatch
 * + the asymmetric POST endpoints (form-config takes path,
 * createField takes body without path).
 *
 * 13 cases.
 */

import { createApplicationFieldsApi } from "../application-fields";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PUT: jest.fn(),
      DELETE: jest.fn(),
    },
    getToken: jest.fn(() => "test-token"),
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

describe("createApplicationFieldsApi", () => {
  // ─── Form config (per-scholarship aggregate) ───────────────────────

  it("getFormConfig GETs /form-config/{scholarship_type} with include_inactive=false default", async () => {
    // Pin: default include_inactive=false. Admin UI should NOT
    // see inactive fields unless explicitly requested. Pin so a
    // refactor flipping the default doesn't silently expose
    // deactivated fields.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createApplicationFieldsApi();
    await api.getFormConfig("phd");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/application-fields/form-config/{scholarship_type}",
      {
        params: {
          path: { scholarship_type: "phd" },
          query: { include_inactive: false },
        },
      }
    );
  });

  it("getFormConfig respects include_inactive=true override", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createApplicationFieldsApi();
    await api.getFormConfig("phd", true);
    expect(
      mockedRaw.GET.mock.calls[0][1].params.query.include_inactive
    ).toBe(true);
  });

  it("saveFormConfig POSTs to /form-config/{scholarship_type} with body", async () => {
    // Pin: ASYMMETRIC POST — takes both path param AND body
    // (unlike createField/createDocument which only take body).
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createApplicationFieldsApi();
    await api.saveFormConfig("phd", { fields: [], documents: [] });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/application-fields/form-config/{scholarship_type}",
      {
        params: { path: { scholarship_type: "phd" } },
        body: { fields: [], documents: [] },
      }
    );
  });

  // ─── Field CRUD ────────────────────────────────────────────────────

  it("getFields GETs /fields/{scholarship_type}", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createApplicationFieldsApi();
    await api.getFields("undergraduate");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/application-fields/fields/{scholarship_type}",
      { params: { path: { scholarship_type: "undergraduate" } } }
    );
  });

  it("createField POSTs body to /fields (no path param)", async () => {
    // Pin: ASYMMETRIC — createField takes body only. The
    // scholarship_type is INSIDE the body, not the URL.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createApplicationFieldsApi();
    await api.createField({
      scholarship_type: "phd",
      field_name: "bank_account",
      field_label: "郵局帳號",
      field_type: "text",
      required: true,
      display_order: 1,
      is_active: true,
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/application-fields/fields",
      {
        body: {
          scholarship_type: "phd",
          field_name: "bank_account",
          field_label: "郵局帳號",
          field_type: "text",
          required: true,
          display_order: 1,
          is_active: true,
        },
      }
    );
  });

  it("updateField PUTs /fields/{field_id}", async () => {
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createApplicationFieldsApi();
    await api.updateField(42, { is_active: false });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/application-fields/fields/{field_id}",
      { params: { path: { field_id: 42 } }, body: { is_active: false } }
    );
  });

  it("deleteField DELETEs /fields/{field_id}", async () => {
    mockedRaw.DELETE.mockResolvedValueOnce(_ok(true));
    const api = createApplicationFieldsApi();
    await api.deleteField(99);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/application-fields/fields/{field_id}",
      { params: { path: { field_id: 99 } } }
    );
  });

  // ─── Document CRUD ─────────────────────────────────────────────────

  it("getDocuments GETs /documents/{scholarship_type}", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createApplicationFieldsApi();
    await api.getDocuments("phd");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/application-fields/documents/{scholarship_type}",
      { params: { path: { scholarship_type: "phd" } } }
    );
  });

  it("createDocument POSTs body to /documents (no path param)", async () => {
    // Pin: same asymmetric pattern as createField.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createApplicationFieldsApi();
    await api.createDocument({
      scholarship_type: "phd",
      document_name: "transcript",
      document_label: "成績單",
      required: true,
      display_order: 1,
      is_active: true,
    });
    expect(mockedRaw.POST.mock.calls[0][0]).toBe(
      "/api/v1/application-fields/documents"
    );
  });

  it("updateDocument PUTs /documents/{document_id}", async () => {
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createApplicationFieldsApi();
    await api.updateDocument(7, { required: false });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/application-fields/documents/{document_id}",
      { params: { path: { document_id: 7 } }, body: { required: false } }
    );
  });

  it("deleteDocument DELETEs /documents/{document_id}", async () => {
    mockedRaw.DELETE.mockResolvedValueOnce(_ok(true));
    const api = createApplicationFieldsApi();
    await api.deleteDocument(7);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/application-fields/documents/{document_id}",
      { params: { path: { document_id: 7 } } }
    );
  });

  it("deleteDocumentExample DELETEs /documents/{id}/example sub-route", async () => {
    // Pin: separate /example sub-route — pin so refactor merging
    // it with /documents/{id} DELETE doesn't accidentally delete
    // the entire document when admin wanted to only clear example.
    mockedRaw.DELETE.mockResolvedValueOnce(_ok(true));
    const api = createApplicationFieldsApi();
    await api.deleteDocumentExample(7);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/application-fields/documents/{document_id}/example",
      { params: { path: { document_id: 7 } } }
    );
  });

  // ─── Verb invariants ───────────────────────────────────────────────

  it("CRUD verb dispatch: GET reads, POST creates, PUT updates, DELETE removes", async () => {
    // Pin: 4 distinct verbs across all 11 methods. Pin so a
    // "RESTful simplification" doesn't collapse update+delete
    // into the same verb.
    mockedRaw.GET.mockResolvedValue(_ok({}));
    mockedRaw.POST.mockResolvedValue(_ok({}));
    mockedRaw.PUT.mockResolvedValue(_ok({}));
    mockedRaw.DELETE.mockResolvedValue(_ok({}));
    const api = createApplicationFieldsApi();
    // 3 reads, 3 creates, 2 updates, 3 deletes
    await api.getFormConfig("p");
    await api.getFields("p");
    await api.getDocuments("p");
    await api.saveFormConfig("p", { fields: [], documents: [] });
    await api.createField({} as any);
    await api.createDocument({} as any);
    await api.updateField(1, {});
    await api.updateDocument(1, {});
    await api.deleteField(1);
    await api.deleteDocument(1);
    await api.deleteDocumentExample(1);
    expect(mockedRaw.GET).toHaveBeenCalledTimes(3);
    expect(mockedRaw.POST).toHaveBeenCalledTimes(3);
    expect(mockedRaw.PUT).toHaveBeenCalledTimes(2);
    expect(mockedRaw.DELETE).toHaveBeenCalledTimes(3);
  });
});
