/**
 * Tests for `frontend/lib/api/modules/payment-rosters.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the admin
 * payment-roster generation UI — critical financial workflow
 * that emits the 造冊 (disbursement roster) Excel sent to
 * accounting.
 *
 * Wave 6a119 pins:
 *  - URL paths + query-param construction
 *  - generateRoster body defaults: student_verification_enabled=
 *    true (SECURITY: verify before paying), auto_export_excel=
 *    true (generate downloadable artifact), force_regenerate=
 *    false (conservative — don't overwrite existing)
 *  - Defaults applied via `??` so explicit false/false-y values
 *    pass through correctly
 *
 * 11 cases.
 */

import { createPaymentRostersApi } from "../payment-rosters";
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

describe("createPaymentRostersApi", () => {
  // ─── getAvailableRankings ──────────────────────────────────────────

  it("getAvailableRankings GETs /available-rankings with required + optional params", async () => {
    mockedRaw.GET.mockResolvedValueOnce(
      _ok({
        rankings: [],
        scholarship_configuration_id: 1,
        academic_year: 114,
      })
    );
    const api = createPaymentRostersApi();
    await api.getAvailableRankings(1, 114, "first");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/payment-rosters/available-rankings",
      {
        params: {
          query: {
            scholarship_configuration_id: 1,
            academic_year: 114,
            semester: "first",
          },
        },
      }
    );
  });

  it("getAvailableRankings omits semester when not provided", async () => {
    // Pin: semester is optional. Pin so a refactor sending
    // explicit null doesn't break backend filter (null != absent).
    mockedRaw.GET.mockResolvedValueOnce(_ok({ rankings: [], scholarship_configuration_id: 1, academic_year: 114 }));
    const api = createPaymentRostersApi();
    await api.getAvailableRankings(1, 114);
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.semester).toBeUndefined();
  });

  // ─── generateRoster body defaults ──────────────────────────────────

  it("generateRoster sets student_verification_enabled=true by default", async () => {
    // Pin SECURITY: disbursement requires verified students.
    // Default ON ensures financial dispatch can't accidentally
    // proceed without verification.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createPaymentRostersApi();
    await api.generateRoster({
      scholarship_configuration_id: 1,
      period_label: "114-1",
      roster_cycle: "monthly",
      academic_year: 114,
    });
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.student_verification_enabled).toBe(true);
  });

  it("generateRoster sets auto_export_excel=true by default", async () => {
    // Pin: default ON — admins expect the downloadable Excel
    // artifact immediately after generation.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createPaymentRostersApi();
    await api.generateRoster({
      scholarship_configuration_id: 1,
      period_label: "x",
      roster_cycle: "yearly",
      academic_year: 114,
    });
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.auto_export_excel).toBe(true);
  });

  it("generateRoster sets force_regenerate=false by default", async () => {
    // Pin SECURITY: conservative — never overwrite an existing
    // roster without explicit consent. Pin so refactor flipping
    // default doesn't silently destroy past disbursement records.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createPaymentRostersApi();
    await api.generateRoster({
      scholarship_configuration_id: 1,
      period_label: "x",
      roster_cycle: "monthly",
      academic_year: 114,
    });
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.force_regenerate).toBe(false);
  });

  it("generateRoster preserves explicit false for student_verification_enabled", async () => {
    // Pin: ?? operator — explicit false passes through (vs
    // OR-default || which would clobber false back to true).
    // Test fixtures or special admin override paths can disable
    // verification explicitly.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createPaymentRostersApi();
    await api.generateRoster({
      scholarship_configuration_id: 1,
      period_label: "x",
      roster_cycle: "monthly",
      academic_year: 114,
      student_verification_enabled: false,
    });
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.student_verification_enabled).toBe(false);
  });

  it("generateRoster preserves explicit false for auto_export_excel", async () => {
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createPaymentRostersApi();
    await api.generateRoster({
      scholarship_configuration_id: 1,
      period_label: "x",
      roster_cycle: "monthly",
      academic_year: 114,
      auto_export_excel: false,
    });
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.auto_export_excel).toBe(false);
  });

  it("generateRoster preserves explicit true for force_regenerate", async () => {
    // Pin: force_regenerate=true explicitly when admin confirms
    // overwrite. Pin so the override path works.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createPaymentRostersApi();
    await api.generateRoster({
      scholarship_configuration_id: 1,
      period_label: "x",
      roster_cycle: "monthly",
      academic_year: 114,
      force_regenerate: true,
    });
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.force_regenerate).toBe(true);
  });

  // ─── getRosters list with filters ──────────────────────────────────

  it("getRosters GETs base path with all optional filters", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createPaymentRostersApi();
    await api.getRosters(5, 114, "draft");
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/payment-rosters", {
      params: {
        query: {
          scholarship_configuration_id: 5,
          academic_year: 114,
          status: "draft",
        },
      },
    });
  });

  it("getRosters omits all filters when none provided", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createPaymentRostersApi();
    await api.getRosters();
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.scholarship_configuration_id).toBeUndefined();
    expect(query.academic_year).toBeUndefined();
    expect(query.status).toBeUndefined();
  });

  // ─── getRoster detail ──────────────────────────────────────────────

  it("getRoster GETs /{id} with path param", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createPaymentRostersApi();
    await api.getRoster(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/payment-rosters/{roster_id}",
      { params: { path: { roster_id: 42 } } }
    );
  });
});

describe("getDistributionDiff", () => {
  it("calls GET with the roster_id path param", async () => {
    const api = createPaymentRostersApi();
    mockedRaw.GET.mockResolvedValue(_ok({ roster_id: 7, to_add: [], to_remove: [] }));

    const res = await api.getDistributionDiff(7);

    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/payment-rosters/{roster_id}/distribution-diff",
      { params: { path: { roster_id: 7 } } }
    );
    expect(res.success).toBe(true);
  });
});

describe("reconcileRoster", () => {
  it("calls POST with path + add/remove body", async () => {
    const api = createPaymentRostersApi();
    mockedRaw.POST.mockResolvedValue(_ok({ added: [], removed: [], excel_stale: true }));

    const res = await api.reconcileRoster(7, {
      add_application_ids: [11],
      remove_item_ids: [22],
      reason: "sync",
    });

    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/payment-rosters/{roster_id}/reconcile",
      {
        params: { path: { roster_id: 7 } },
        body: { add_application_ids: [11], remove_item_ids: [22], reason: "sync" },
      }
    );
    expect(res.success).toBe(true);
  });
});

describe("restoreRosterItem", () => {
  it("restoreRosterItem POSTs to the restore path with reason_note", async () => {
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createPaymentRostersApi();
    await api.restoreRosterItem(7, 42, "誤刪");
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/payment-rosters/{roster_id}/items/{item_id}/restore",
      {
        params: { path: { roster_id: 7, item_id: 42 } },
        body: { reason_note: "誤刪" },
      }
    );
  });

  it("restoreRosterItem sends reason_note=null when omitted", async () => {
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createPaymentRostersApi();
    await api.restoreRosterItem(1, 2);
    expect(mockedRaw.POST.mock.calls[0][1].body).toEqual({ reason_note: null });
  });
});
