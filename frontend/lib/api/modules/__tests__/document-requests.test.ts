/**
 * Tests for `frontend/lib/api/modules/document-requests.ts`.
 *
 * Module had ZERO dedicated test coverage. Smallest module
 * in api/modules — just 2 student-facing endpoints (view +
 * fulfill document requests).
 *
 * Wave 6a134 pins URL paths + verb dispatch + the optional-
 * vs-conditional body for fulfill (only sends body when notes
 * provided).
 *
 * 8 cases.
 */

import { createDocumentRequestsApi } from "../document-requests";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      PATCH: jest.fn(),
    },
  },
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  PATCH: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createDocumentRequestsApi", () => {
  // ─── getMyDocumentRequests ─────────────────────────────────────────

  it("getMyDocumentRequests GETs /my-requests with no query when no filter", async () => {
    // Pin: when no status filter, params.query is undefined
    // (NOT empty object). Pin so refactor sending {} doesn't
    // break some backend validators.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createDocumentRequestsApi();
    await api.getMyDocumentRequests();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/document-requests/my-requests",
      { params: { query: undefined } }
    );
  });

  it("getMyDocumentRequests forwards status filter when provided", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createDocumentRequestsApi();
    await api.getMyDocumentRequests("pending");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/document-requests/my-requests",
      { params: { query: { status: "pending" } } }
    );
  });

  it("getMyDocumentRequests uses /my-requests sub-route (student-scoped)", async () => {
    // Pin: /my-requests is student-scoped — backend filters to
    // current user's requests. Pin so refactor to /admin path
    // breaks student-facing UI auth.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createDocumentRequestsApi();
    await api.getMyDocumentRequests();
    expect(mockedRaw.GET.mock.calls[0][0]).toContain("/my-requests");
  });

  // ─── fulfillDocumentRequest ────────────────────────────────────────

  it("fulfillDocumentRequest PATCHes /{request_id}/fulfill", async () => {
    // Pin: PATCH (state transition pending → fulfilled), NOT
    // POST. Pin so refactor doesn't change semantics.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createDocumentRequestsApi();
    await api.fulfillDocumentRequest(42);
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/document-requests/{request_id}/fulfill",
      { params: { path: { request_id: 42 } }, body: undefined }
    );
  });

  it("fulfillDocumentRequest sends body ONLY when notes provided", async () => {
    // Pin: body is {notes} when notes provided, undefined when
    // not. Pin so refactor doesn't accidentally always send
    // {notes: undefined} which some backends treat as
    // "explicitly null".
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createDocumentRequestsApi();
    await api.fulfillDocumentRequest(42, "uploaded all required docs");
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/document-requests/{request_id}/fulfill",
      {
        params: { path: { request_id: 42 } },
        body: { notes: "uploaded all required docs" },
      }
    );
  });

  it("fulfillDocumentRequest body is undefined when no notes", async () => {
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createDocumentRequestsApi();
    await api.fulfillDocumentRequest(42);
    expect(mockedRaw.PATCH.mock.calls[0][1].body).toBeUndefined();
  });

  it("fulfillDocumentRequest body is undefined when empty notes", async () => {
    // Pin: empty string notes → undefined body (NOT {notes: ""}).
    // Falsy check applied — pin so refactor doesn't accidentally
    // send empty-string notes to backend.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createDocumentRequestsApi();
    await api.fulfillDocumentRequest(42, "");
    expect(mockedRaw.PATCH.mock.calls[0][1].body).toBeUndefined();
  });

  // ─── Read-only verb mix invariant ─────────────────────────────────

  it("module exposes only 2 methods (GET + PATCH; no POST/PUT/DELETE)", async () => {
    // Pin: tiny module — only student-facing view and fulfill.
    // No create/delete (admin-side operations live elsewhere).
    // Pin so refactor accidentally adding cancelRequest /
    // createRequest in this student module requires explicit
    // auth-scope review.
    const api = createDocumentRequestsApi();
    expect(api.getMyDocumentRequests).toBeDefined();
    expect(api.fulfillDocumentRequest).toBeDefined();
    expect(Object.keys(api).length).toBe(3);
  });
});
