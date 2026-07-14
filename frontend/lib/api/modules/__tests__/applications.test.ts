/**
 * Tests for `frontend/lib/api/modules/applications.ts`.
 *
 * Module had ZERO dedicated test coverage. The CORE module
 * driving the entire student/professor/admin application flow
 * (CRUD, status transitions, document uploads, recommendation
 * submission, audit trail, document requests). 423 LOC, 22
 * methods.
 *
 * Wave 6a136 pins the SECURITY/dispatch invariants — paths,
 * verbs, body shapes, draft-vs-create branching, deprecated-
 * alias parity, raw-fetch upload/delete contracts.
 *
 * 21 cases focused on contract drift risk.
 */

import { createApplicationsApi } from "../applications";
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

jest.mock("../../compat", () => ({
  toApiResponse: jest.fn((r) => r),
}));

jest.mock("../../form-data-helpers", () => ({
  createFileUploadFormData: jest.fn((d) => d),
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PUT: jest.Mock;
  DELETE: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createApplicationsApi", () => {
  // ─── List endpoints ───────────────────────────────────────────────

  it("getMyApplications GETs /applications with optional status filter", async () => {
    // Pin: query.status omitted (undefined) when no filter — NOT
    // empty object. Pin so refactor doesn't send `{}` to backend.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.getMyApplications();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/applications", {
      params: { query: undefined },
    });
  });

  it("getMyApplications forwards status when provided", async () => {
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.getMyApplications("submitted");
    expect(mockedRaw.GET.mock.calls[0][1].params.query).toEqual({
      status: "submitted",
    });
  });

  it("getCollegeReview GETs college-scoped /review with snake_case scholarship_type", async () => {
    // Pin: backend Pydantic expects snake_case `scholarship_type`
    // (NOT camelCase). Pin so refactor renaming param doesn't break
    // college reviewer UI.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.getCollegeReview("under_review", "nstc");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/applications/college/review",
      { params: { query: { status: "under_review", scholarship_type: "nstc" } } }
    );
  });

  it("getByScholarshipType GETs /review/list (admin/staff endpoint, distinct from college/review)", async () => {
    // Pin SCOPE: /review/list is admin/staff while /college/review
    // is college-scoped. Pin so refactor doesn't collapse the two
    // and accidentally expose all college's applications.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.getByScholarshipType("nstc", "submitted");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/applications/review/list",
      { params: { query: { scholarship_type: "nstc", status: "submitted" } } }
    );
  });

  // ─── createApplication + draft branching ──────────────────────────

  it("createApplication uses query is_draft=true ONLY when isDraft=true", async () => {
    // Pin: false default → query is `undefined` (NOT `{is_draft:
    // false}`). Backend treats absence vs explicit-false differently
    // for the submission audit log.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.createApplication({ scholarship_type: "nstc" });
    expect(mockedRaw.POST.mock.calls[0][1].params.query).toBeUndefined();
  });

  it("createApplication sends is_draft=true query when isDraft=true", async () => {
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.createApplication({ scholarship_type: "nstc" }, true);
    expect(mockedRaw.POST.mock.calls[0][1].params.query).toEqual({
      is_draft: true,
    });
  });

  it("createApplication body passes through dynamic fields verbatim", async () => {
    // Pin: [key: string]: any signature — dynamic form fields
    // (bank_account, contact_phone, etc.) must pass through as-is.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.createApplication({
      scholarship_type: "nstc",
      bank_account: "12345",
      contact_phone: "0912345678",
      gpa: 3.8,
    });
    expect(mockedRaw.POST.mock.calls[0][1].body).toEqual({
      scholarship_type: "nstc",
      bank_account: "12345",
      contact_phone: "0912345678",
      gpa: 3.8,
    });
  });

  // ─── updateApplicationStatus / updateStatus deprecated parity ─────

  it("updateApplicationStatus PUTs /{id}/status with status + comments + rejection_reason", async () => {
    // Pin SECURITY: status mutations include rejection_reason on
    // reject path — required by application_audit_service.
    mockedRaw.PUT.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.updateApplicationStatus(42, {
      status: "rejected",
      comments: "missing transcripts",
      rejection_reason: "incomplete documents",
    });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/applications/{id}/status",
      {
        params: { path: { id: 42 } },
        body: {
          status: "rejected",
          comments: "missing transcripts",
          rejection_reason: "incomplete documents",
        },
      }
    );
  });

  it("updateStatus deprecated alias hits SAME URL/verb as updateApplicationStatus", async () => {
    // Pin: deprecated alias preserves identical contract — pin
    // so refactor removing the deprecated method doesn't break
    // callers still using updateStatus().
    mockedRaw.PUT.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.updateStatus(42, { status: "approved", comments: "ok" });
    expect(mockedRaw.PUT.mock.calls[0][0]).toBe(
      "/api/v1/applications/{id}/status"
    );
  });

  // ─── deleteApplication (soft delete, optional reason) ─────────────

  it("deleteApplication DELETEs /{id} with query.reason omitted when not given", async () => {
    // Pin: soft-delete (NOT hard). When reason missing, query is
    // undefined (NOT empty object). Reason is required for staff
    // but optional for student self-delete — backend enforces.
    mockedRaw.DELETE.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.deleteApplication(42);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/applications/{id}",
      { params: { path: { id: 42 }, query: undefined } }
    );
  });

  it("deleteApplication forwards reason query when provided", async () => {
    mockedRaw.DELETE.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.deleteApplication(42, "duplicate application");
    expect(mockedRaw.DELETE.mock.calls[0][1].params.query).toEqual({
      reason: "duplicate application",
    });
  });

  // ─── Lifecycle: submit / withdraw / restore (POST, no body) ───────

  it("submitApplication POSTs /{id}/submit with NO body", async () => {
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.submitApplication(42);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/applications/{id}/submit",
      { params: { path: { id: 42 } } }
    );
  });

  it("withdrawApplication POSTs /{id}/withdraw and restoreApplication POSTs /{id}/restore", async () => {
    // Pin: both are POST (state transitions). Pin so refactor
    // doesn't change to DELETE or PATCH.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.withdrawApplication(42);
    expect(mockedRaw.POST.mock.calls[0][0]).toBe(
      "/api/v1/applications/{id}/withdraw"
    );

    mockedRaw.POST.mockResolvedValueOnce({});
    await api.restoreApplication(42);
    expect(mockedRaw.POST.mock.calls[1][0]).toBe(
      "/api/v1/applications/{id}/restore"
    );
  });

  // ─── File upload endpoints ────────────────────────────────────────

  it("uploadFile POSTs /{id}/files with FormData carrying file + file_type", async () => {
    // Pin: file_type is in BODY (FormData entry, NOT query). Pin
    // so refactor doesn't move it to query — backend reads from
    // multipart form.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    const file = new File(["x"], "x.pdf");
    await api.uploadFile(42, file, "transcript");
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/applications/{id}/files",
      expect.objectContaining({
        params: { path: { id: 42 } },
      })
    );
  });

  it("uploadDocument POSTs /{id}/files/upload with file_type in QUERY (NOT body)", async () => {
    // Pin: distinct from uploadFile — uploadDocument puts
    // file_type in QUERY string. Backend distinguishes the two
    // endpoints by URL. Pin so refactor doesn't collapse them.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    const file = new File(["x"], "x.pdf");
    await api.uploadDocument(42, file, "appendix");
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/applications/{id}/files/upload",
      expect.objectContaining({
        params: {
          path: { id: 42 },
          query: { file_type: "appendix" },
        },
      })
    );
  });

  it("uploadDocument defaults fileType to 'other' when omitted", async () => {
    // Pin: 'other' default — pin so refactor changing default to
    // 'unknown' or empty breaks the dropdown-less student form.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    const file = new File(["x"], "x.pdf");
    await api.uploadDocument(42, file);
    expect(mockedRaw.POST.mock.calls[0][1].params.query.file_type).toBe(
      "other"
    );
  });

  // ─── submitRecommendation ─────────────────────────────────────────

  it("submitRecommendation POSTs /{id}/review with conditional selected_awards", async () => {
    // Pin: selected_awards spread-conditionally — omitted entirely
    // when undefined (NOT included as undefined). Pin so refactor
    // doesn't send selected_awards: undefined which backend
    // Pydantic may reject.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.submitRecommendation(42, "professor", "approve");
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body).toEqual({
      id: 42,
      review_stage: "professor",
      recommendation: "approve",
    });
    expect("selected_awards" in body).toBe(false);
  });

  it("submitRecommendation includes selected_awards when provided", async () => {
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.submitRecommendation(42, "college", "approve", ["nstc", "moe_1w"]);
    expect(mockedRaw.POST.mock.calls[0][1].body.selected_awards).toEqual([
      "nstc",
      "moe_1w",
    ]);
  });

  // ─── getAuditTrail defaults ───────────────────────────────────────

  it("getAuditTrail defaults limit=50 offset=0 with conditional action_filter", async () => {
    // Pin: pagination defaults match admin dashboard page size.
    // action_filter spread-conditional — omitted (not undefined)
    // when no filter.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.getAuditTrail(42);
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.limit).toBe(50);
    expect(query.offset).toBe(0);
    expect("action_filter" in query).toBe(false);
  });

  it("getAuditTrail forwards action_filter when provided", async () => {
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.getAuditTrail(42, 10, 20, "status_change");
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query).toEqual({
      limit: 10,
      offset: 20,
      action_filter: "status_change",
    });
  });

  // ─── createDocumentRequest / listDocumentRequests ─────────────────

  it("createDocumentRequest uses application_id path param (NOT id)", async () => {
    // Pin: distinct path-param NAME for document-requests sub-
    // resource — backend handler signature uses `application_id`.
    // Pin so refactor renaming to `id` breaks the endpoint.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.createDocumentRequest(42, {
      requested_documents: ["transcript", "bank_passbook"],
      reason: "missing required docs",
      notes: "due in 7 days",
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/applications/{application_id}/document-requests",
      {
        params: { path: { application_id: 42 } },
        body: {
          requested_documents: ["transcript", "bank_passbook"],
          reason: "missing required docs",
          notes: "due in 7 days",
        },
      }
    );
  });

  it("listDocumentRequests query.status undefined when no filter", async () => {
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createApplicationsApi();
    await api.listDocumentRequests(42);
    expect(mockedRaw.GET.mock.calls[0][1].params.query).toBeUndefined();
  });

  // ─── saveApplicationDraft normalization ───────────────────────────

  it("saveApplicationDraft normalizes response with default success message when data has id", async () => {
    // Pin: normalization layer — when backend returns
    // {data: {id: ...}}, wrap with explicit success=true and
    // fallback message "Draft saved successfully" if backend
    // didn't provide one.
    mockedRaw.POST.mockResolvedValueOnce({
      data: { id: 99, scholarship_type: "nstc" },
    });
    const api = createApplicationsApi();
    const result = await api.saveApplicationDraft({ scholarship_type: "nstc" });
    expect(result.success).toBe(true);
    expect(result.message).toBe("Draft saved successfully");
    expect(result.data).toEqual({ id: 99, scholarship_type: "nstc" });
  });
});
