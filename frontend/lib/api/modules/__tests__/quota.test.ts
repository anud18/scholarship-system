/**
 * Tests for `frontend/lib/api/modules/quota.ts` createQuotaApi
 * factory (the helper functions calculateTotalQuota /
 * calculateUsagePercentage / getQuotaStatusColor are covered
 * by wave 6nn in lib/__tests__/quota-utils.test.ts).
 *
 * Module's createQuotaApi factory had ZERO dedicated test
 * coverage. Drives the admin quota management UI — critical
 * for verifying available quotas before disbursement.
 *
 * Wave 6a123 pins URL paths + path templating + body shapes +
 * the batchUpdateMatrixQuotas client-side aggregation logic.
 *
 * 12 cases.
 */

import { createQuotaApi } from "../quota";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PUT: jest.fn(),
    },
    getToken: jest.fn(() => "test-token"),
  },
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PUT: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

function _fail(message: string) {
  return {
    data: { success: false, message, data: null },
    response: { ok: false, status: 400 },
  };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createQuotaApi", () => {
  // ─── Available semesters ───────────────────────────────────────────

  it("getAvailableSemesters GETs /available-semesters with optional mode", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createQuotaApi();
    await api.getAvailableSemesters("simple");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/available-semesters",
      { params: { query: { quota_management_mode: "simple" } } }
    );
  });

  it("getAvailableSemesters omits query mode when undefined", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createQuotaApi();
    await api.getAvailableSemesters();
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.quota_management_mode).toBeUndefined();
  });

  // ─── Path templating ───────────────────────────────────────────────

  it("getQuotaOverview templates period into path", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createQuotaApi();
    await api.getQuotaOverview("114-1");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/overview/{period}",
      { params: { path: { period: "114-1" } } }
    );
  });

  it("getMatrixQuotaStatus templates period into path", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createQuotaApi();
    await api.getMatrixQuotaStatus("113-2");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/matrix-quota-status/{period}",
      { params: { path: { period: "113-2" } } }
    );
  });

  // ─── updateMatrixQuota ─────────────────────────────────────────────

  it("updateMatrixQuota PUTs body with sub_type/college/new_quota keys", async () => {
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createQuotaApi();
    await api.updateMatrixQuota({
      academic_year: 114,
      sub_type: "nstc",
      college: "A",
      new_quota: 12,
    });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/matrix-quota",
      { body: { academic_year: 114, sub_type: "nstc", college: "A", new_quota: 12 } }
    );
  });

  // ─── batchUpdateMatrixQuotas client-side aggregation ──────────────

  it("batchUpdateMatrixQuotas calls updateMatrixQuota once per entry", async () => {
    // Pin: client-side batch loop. Pin so a refactor that moves
    // batching to a server-side endpoint requires explicit
    // backend route + this test update.
    mockedRaw.PUT.mockResolvedValue(_ok({ updated: true }));
    const api = createQuotaApi();
    const updates = [
      { sub_type: "nstc", college: "A", new_quota: 1 },
      { sub_type: "nstc", college: "B", new_quota: 2 },
      { sub_type: "moe", college: "A", new_quota: 3 },
    ];
    await api.batchUpdateMatrixQuotas(updates);
    expect(mockedRaw.PUT).toHaveBeenCalledTimes(3);
  });

  it("batchUpdateMatrixQuotas success when all succeed", async () => {
    mockedRaw.PUT.mockResolvedValue(_ok({ x: 1 }));
    const api = createQuotaApi();
    const result = await api.batchUpdateMatrixQuotas([
      { sub_type: "a", college: "A", new_quota: 1 },
    ]);
    expect(result.success).toBe(true);
    expect(result.errors).toBeUndefined();
  });

  it("batchUpdateMatrixQuotas reports per-row error when one fails", async () => {
    // Pin: partial-failure aggregation — first row succeeds,
    // second fails. Result.success=false, errors array contains
    // the failed row description. CRITICAL for admin UX:
    // batch view shows which specific updates failed.
    mockedRaw.PUT.mockResolvedValueOnce(_ok({ x: 1 }))
      .mockResolvedValueOnce(_fail("Quota exceeds total"));
    const api = createQuotaApi();
    const result = await api.batchUpdateMatrixQuotas([
      { sub_type: "nstc", college: "A", new_quota: 1 },
      { sub_type: "nstc", college: "B", new_quota: 100 },
    ]);
    expect(result.success).toBe(false);
    expect(result.errors).toHaveLength(1);
    expect(result.errors![0]).toContain("nstc-B");
    expect(result.errors![0]).toContain("Quota exceeds total");
  });

  it("batchUpdateMatrixQuotas catches thrown exceptions per row", async () => {
    // Pin: per-row try/catch — a network error on row N doesn't
    // abort rows N+1, N+2, etc. Resilience for admin batch ops.
    mockedRaw.PUT.mockResolvedValueOnce(_ok({ x: 1 }))
      .mockRejectedValueOnce(new Error("network fail"));
    const api = createQuotaApi();
    const result = await api.batchUpdateMatrixQuotas([
      { sub_type: "nstc", college: "A", new_quota: 1 },
      { sub_type: "nstc", college: "B", new_quota: 2 },
    ]);
    expect(mockedRaw.PUT).toHaveBeenCalledTimes(2); // Both attempted
    expect(result.success).toBe(false);
    expect(result.errors![0]).toContain("Error updating");
  });

  // ─── List endpoints ────────────────────────────────────────────────

  it("getCollegeConfigs GETs /colleges", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createQuotaApi();
    await api.getCollegeConfigs();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/colleges"
    );
  });

  it("getScholarshipTypeConfigs GETs /scholarship-types", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createQuotaApi();
    await api.getScholarshipTypeConfigs();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/scholarship-types"
    );
  });

  // ─── validateQuotaChange ───────────────────────────────────────────

  it("validateQuotaChange POSTs to /validate-quota with body", async () => {
    // Pin: dedicated validation endpoint — admin UI checks
    // proposed changes BEFORE committing.
    mockedRaw.POST.mockResolvedValueOnce(_ok({ valid: true, warnings: [] }));
    const api = createQuotaApi();
    await api.validateQuotaChange({ sub_type: "nstc", college: "A", new_quota: 5 });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/validate-quota",
      { body: { sub_type: "nstc", college: "A", new_quota: 5 } }
    );
  });

  // ─── getQuotaHistory ───────────────────────────────────────────────

  it("getQuotaHistory uses limit=50 default", async () => {
    // Pin: default 50 entries (admin UI page size). Pin so a
    // refactor changing the default doesn't silently shrink/
    // grow the visible history.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createQuotaApi();
    await api.getQuotaHistory("114");
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.limit).toBe(50);
    expect(query.academic_year).toBe("114");
  });
});
