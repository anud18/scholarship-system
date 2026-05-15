/**
 * Tests for `frontend/lib/api/modules/bank-verification.ts`.
 *
 * Module had ZERO dedicated test coverage. SECURITY-CRITICAL —
 * bank verification gates disbursement to students.
 *
 * Wave 6a130 pins URL paths + body shapes + the SECURITY-
 * relevant default `force_recheck=false` (don't re-OCR
 * already-verified accounts unless admin explicitly requests).
 *
 * 11 cases.
 */

import { createBankVerificationApi } from "../bank-verification";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
    },
  },
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createBankVerificationApi", () => {
  // ─── getBankVerificationInitData ───────────────────────────────────

  it("getBankVerificationInitData GETs /admin/bank-verification/{id}/init", async () => {
    // Pin: dedicated /init sub-route returns initial data WITHOUT
    // performing OCR. Used for direct manual review mode — admin
    // bypasses automated verification. Pin so refactor doesn't
    // accidentally trigger OCR (slow + bills the AI provider).
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createBankVerificationApi();
    await api.getBankVerificationInitData(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/admin/bank-verification/{application_id}/init",
      { params: { path: { application_id: 42 } } }
    );
  });

  // ─── verifyBankAccount + force_recheck default ─────────────────────

  it("verifyBankAccount sets force_recheck=false by default", async () => {
    // Pin SECURITY: default force_recheck=false prevents re-OCR
    // of already-verified accounts. Pin so refactor flipping
    // default to true doesn't burn AI provider budget or
    // produce false re-verification failures.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBankVerificationApi();
    await api.verifyBankAccount(42);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/admin/bank-verification",
      { body: { application_id: 42, force_recheck: false } }
    );
  });

  it("verifyBankAccount allows explicit force_recheck=true", async () => {
    // Pin: admin can opt-in to re-verify (e.g., after upload of
    // new passbook image).
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBankVerificationApi();
    await api.verifyBankAccount(42, true);
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.force_recheck).toBe(true);
  });

  // ─── verifyBankAccountsBatch ──────────────────────────────────────

  it("verifyBankAccountsBatch POSTs /batch with application_ids array", async () => {
    // Pin: synchronous batch endpoint — body has application_ids
    // (plural, snake_case). Pin so refactor renaming to
    // applicationIds breaks backend Pydantic.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBankVerificationApi();
    await api.verifyBankAccountsBatch([1, 2, 3]);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/admin/bank-verification/batch",
      { body: { application_ids: [1, 2, 3], force_recheck: false } }
    );
  });

  it("verifyBankAccountsBatch inherits force_recheck=false default", async () => {
    // Pin: same SECURITY default as single verify.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBankVerificationApi();
    await api.verifyBankAccountsBatch([1, 2]);
    expect(mockedRaw.POST.mock.calls[0][1].body.force_recheck).toBe(false);
  });

  // ─── submitManualReview ───────────────────────────────────────────

  it("submitManualReview POSTs /manual-review with review payload", async () => {
    // Pin: SECURITY — manual review is the override path that
    // bypasses OCR result. Admin must explicitly approve/correct
    // each field. Body includes optional account_number_approved
    // + account_number_corrected (and same for holder).
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBankVerificationApi();
    await api.submitManualReview({
      application_id: 42,
      account_number_approved: true,
      account_number_corrected: "12345-67890",
      account_holder_approved: true,
      account_holder_corrected: "王小明",
      review_notes: "OCR mismatch — verified manually with bank passbook",
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/admin/bank-verification/manual-review",
      {
        body: {
          application_id: 42,
          account_number_approved: true,
          account_number_corrected: "12345-67890",
          account_holder_approved: true,
          account_holder_corrected: "王小明",
          review_notes: "OCR mismatch — verified manually with bank passbook",
        },
      }
    );
  });

  // ─── Async batch verification ──────────────────────────────────────

  it("startBatchVerificationAsync POSTs /batch-async with NO force_recheck", async () => {
    // Pin: async batch doesn't accept force_recheck — server-side
    // policy controls re-verification on async path. Pin so a
    // refactor adding force_recheck silently affects the contract.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createBankVerificationApi();
    await api.startBatchVerificationAsync([1, 2, 3]);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/admin/bank-verification/batch-async",
      { body: { application_ids: [1, 2, 3] } }
    );
  });

  it("getVerificationTaskStatus GETs /tasks/{task_id}", async () => {
    // Pin: task_id is a STRING (UUID), not number. Pin path
    // templating with snake_case key.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createBankVerificationApi();
    await api.getVerificationTaskStatus("uuid-abc-123");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/admin/bank-verification/tasks/{task_id}",
      { params: { path: { task_id: "uuid-abc-123" } } }
    );
  });

  it("listVerificationTasks defaults limit=50 offset=0", async () => {
    // Pin: pagination defaults match the admin dashboard's
    // page size. Pin so refactor doesn't silently change
    // pagination on the task-list view.
    mockedRaw.GET.mockResolvedValueOnce(_ok({ tasks: [], pagination: {} }));
    const api = createBankVerificationApi();
    await api.listVerificationTasks();
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.limit).toBe(50);
    expect(query.offset).toBe(0);
    expect(query.status).toBeUndefined();
  });

  it("listVerificationTasks forwards status filter", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({ tasks: [], pagination: {} }));
    const api = createBankVerificationApi();
    await api.listVerificationTasks("processing", 10, 20);
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.status).toBe("processing");
    expect(query.limit).toBe(10);
    expect(query.offset).toBe(20);
  });

  // ─── Student endpoint (different scope from admin /*) ─────────────

  it("getMyVerifiedAccount GETs student endpoint (NOT /admin)", async () => {
    // Pin SCOPE: getMyVerifiedAccount is under /student-bank-
    // accounts/ (NOT /admin/bank-verification/). Student endpoint
    // returns ONLY the current student's account. Pin so refactor
    // moving it to /admin breaks the student-facing UI auth.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createBankVerificationApi();
    await api.getMyVerifiedAccount();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/student-bank-accounts/my-verified-account"
    );
  });
});
