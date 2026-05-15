/**
 * Tests for `frontend/lib/api/modules/batch-import.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the college
 * batch-import flow (upload Excel → preview → fix → confirm →
 * upload documents ZIP). High-risk workflow — silent regression
 * can either:
 *   - Misroute a wrong-college batch to /confirm
 *   - Confirm a batch when admin only wanted to preview
 *   - Delete documents/records belonging to wrong batch
 *
 * Wave 6a127 pins URL paths + verb dispatch + the SECURITY-
 * relevant /confirm body shape with confirm=true default.
 *
 * 13 cases.
 */

import { createBatchImportApi } from "../batch-import";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PATCH: jest.fn(),
      DELETE: jest.fn(),
    },
    getToken: jest.fn(() => "test-token"),
  },
}));

jest.mock("../../form-data-helpers", () => ({
  createFileUploadFormData: jest.fn((data) => ({ __formData: data })),
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PATCH: jest.Mock;
  DELETE: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createBatchImportApi", () => {
  // ─── uploadData (Excel/CSV with query params) ──────────────────────

  it("uploadData POSTs /upload-data with query + FormData body", async () => {
    // Pin: scholarship_type/academic_year/semester go via QUERY,
    // not body. Pin so a refactor to body breaks the multipart
    // contract (form file in body, metadata in query).
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    const fakeFile = new File(["x"], "test.xlsx");
    await api.uploadData(fakeFile, "phd", 114, "first");
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/college-review/batch-import/upload-data",
      expect.objectContaining({
        params: {
          query: {
            scholarship_type: "phd",
            academic_year: 114,
            semester: "first",
          },
        },
      })
    );
  });

  // ─── confirm (SECURITY: default confirm=true) ──────────────────────

  it("confirm POSTs /{batch_id}/confirm with confirm=true default", async () => {
    // Pin SECURITY: default confirm=true means calling
    // api.confirm(7) confirms by default — pin so refactor
    // changing the default to false doesn't silently turn
    // confirmations into no-ops.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    await api.confirm(7);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/college-review/batch-import/{batch_id}/confirm",
      { params: { path: { batch_id: 7 } }, body: { batch_id: 7, confirm: true } }
    );
  });

  it("confirm body duplicates batch_id (path AND body)", async () => {
    // Pin: the body redundantly includes batch_id. Likely
    // legacy contract — pin so refactor removing it doesn't
    // silently break backend handler that reads from body.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    await api.confirm(42, false);
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.batch_id).toBe(42);
    expect(body.confirm).toBe(false);
  });

  // ─── updateRecord ──────────────────────────────────────────────────

  it("updateRecord PATCHes /{batch_id}/records with record_index in body", async () => {
    // Pin: PATCH semantics — partial update of a single row.
    // record_index goes via body, not path (unlike deleteRecord).
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    await api.updateRecord(7, 3, { gpa: 3.9 });
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/college-review/batch-import/{batch_id}/records",
      {
        params: { path: { batch_id: 7 } },
        body: { record_index: 3, updates: { gpa: 3.9 } },
      }
    );
  });

  // ─── revalidate ────────────────────────────────────────────────────

  it("revalidate POSTs /{batch_id}/validate (no body)", async () => {
    // Pin: validate-only POST — pure side-effect, server reruns
    // validation on stored data.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    await api.revalidate(7);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/college-review/batch-import/{batch_id}/validate",
      { params: { path: { batch_id: 7 } } }
    );
  });

  // ─── deleteRecord (record_index in PATH, unlike update) ────────────

  it("deleteRecord DELETEs /{batch_id}/records/{record_index}", async () => {
    // Pin ASYMMETRY: update has record_index in BODY,
    // delete has it in PATH. Pin both contracts to document
    // the divergence — easy to "fix consistency" and break one.
    mockedRaw.DELETE.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    await api.deleteRecord(7, 3);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/college-review/batch-import/{batch_id}/records/{record_index}",
      { params: { path: { batch_id: 7, record_index: 3 } } }
    );
  });

  // ─── uploadDocuments (ZIP file) ────────────────────────────────────

  it("uploadDocuments POSTs /{batch_id}/documents with ZIP FormData", async () => {
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    const zipFile = new File(["zip"], "docs.zip");
    await api.uploadDocuments(7, zipFile);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/college-review/batch-import/{batch_id}/documents",
      expect.objectContaining({ params: { path: { batch_id: 7 } } })
    );
  });

  // ─── getHistory ────────────────────────────────────────────────────

  it("getHistory GETs /history with optional pagination + status", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    await api.getHistory({ skip: 0, limit: 50, status: "completed" });
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/college-review/batch-import/history",
      { params: { query: { skip: 0, limit: 50, status: "completed" } } }
    );
  });

  it("getHistory undefined-fills all 3 query params when omitted", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    await api.getHistory();
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.skip).toBeUndefined();
    expect(query.limit).toBeUndefined();
    expect(query.status).toBeUndefined();
  });

  // ─── getDetails ────────────────────────────────────────────────────

  it("getDetails GETs /{batch_id}/details", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    await api.getDetails(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/college-review/batch-import/{batch_id}/details",
      { params: { path: { batch_id: 42 } } }
    );
  });

  // ─── deleteBatch ────────────────────────────────────────────────────

  it("deleteBatch DELETEs /{batch_id} (no records sub-route)", async () => {
    // Pin: top-level DELETE on /{batch_id} removes the entire
    // batch AND its applications. Pin so refactor doesn't
    // accidentally route this to /records (which would only
    // delete a single record).
    mockedRaw.DELETE.mockResolvedValueOnce(_ok({}));
    const api = createBatchImportApi();
    await api.deleteBatch(42);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/college-review/batch-import/{batch_id}",
      { params: { path: { batch_id: 42 } } }
    );
  });

  // ─── All paths share /college-review/batch-import base ─────────────

  it("all paths share /api/v1/college-review/batch-import base", async () => {
    mockedRaw.GET.mockResolvedValue(_ok({}));
    mockedRaw.POST.mockResolvedValue(_ok({}));
    mockedRaw.PATCH.mockResolvedValue(_ok({}));
    mockedRaw.DELETE.mockResolvedValue(_ok({}));
    const api = createBatchImportApi();
    await api.uploadData(new File([""], "x"), "p", 1, "first");
    await api.confirm(1);
    await api.updateRecord(1, 0, {});
    await api.revalidate(1);
    await api.deleteRecord(1, 0);
    await api.uploadDocuments(1, new File([""], "x"));
    await api.getHistory();
    await api.getDetails(1);
    await api.deleteBatch(1);
    const allPaths = [
      ...mockedRaw.GET.mock.calls.map((c) => c[0]),
      ...mockedRaw.POST.mock.calls.map((c) => c[0]),
      ...mockedRaw.PATCH.mock.calls.map((c) => c[0]),
      ...mockedRaw.DELETE.mock.calls.map((c) => c[0]),
    ];
    for (const path of allPaths) {
      expect(path).toMatch(
        /^\/api\/v1\/college-review\/batch-import/
      );
    }
  });

  // ─── Verb dispatch ─────────────────────────────────────────────────

  it("CRUD-like verb dispatch: GET reads, POST creates+validates, PATCH partial-updates, DELETE removes", async () => {
    mockedRaw.GET.mockResolvedValue(_ok({}));
    mockedRaw.POST.mockResolvedValue(_ok({}));
    mockedRaw.PATCH.mockResolvedValue(_ok({}));
    mockedRaw.DELETE.mockResolvedValue(_ok({}));
    const api = createBatchImportApi();

    await api.getHistory(); // GET
    await api.getDetails(1); // GET
    await api.uploadData(new File([""], "x"), "p", 1, "first"); // POST
    await api.confirm(1); // POST
    await api.revalidate(1); // POST
    await api.uploadDocuments(1, new File([""], "x")); // POST
    await api.updateRecord(1, 0, {}); // PATCH
    await api.deleteRecord(1, 0); // DELETE
    await api.deleteBatch(1); // DELETE

    expect(mockedRaw.GET).toHaveBeenCalledTimes(2);
    expect(mockedRaw.POST).toHaveBeenCalledTimes(4);
    expect(mockedRaw.PATCH).toHaveBeenCalledTimes(1);
    expect(mockedRaw.DELETE).toHaveBeenCalledTimes(2);
  });
});
