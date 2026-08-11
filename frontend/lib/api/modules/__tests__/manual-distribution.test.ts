/**
 * Tests for `frontend/lib/api/modules/manual-distribution.ts`.
 *
 * Module had ZERO dedicated test coverage. SECURITY-CRITICAL —
 * controls scholarship allocation (who gets paid, how much, and
 * for which year/sub-type). Drift in body shape or path templating
 * would silently misallocate funds.
 *
 * Wave 6a135 pins the methods: URL paths, body shapes, path-
 * templated history/restore, and query-spread of optional college_code.
 *
 * 30 cases.
 */

import {
  createManualDistributionApi,
  exportDistributionSummary,
  isCancelledAllocation,
  mergeSuggestions,
  reasonsBySuggestion,
  summarizeReasons,
  toStagedItems,
  unallocatedReasonLabel,
  UNALLOCATED_REASON_LABEL,
  type UnallocatedReason,
} from "../manual-distribution";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
    },
    getToken: jest.fn(() => "test-token"),
  },
}));

jest.mock("../../compat", () => ({
  toApiResponse: jest.fn((r) => r),
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createManualDistributionApi", () => {
  // ─── getAvailableCombinations ─────────────────────────────────────

  it("getAvailableCombinations GETs /available-combinations with no params", async () => {
    // Pin: enumeration endpoint — no filters. Pin so refactor
    // adding query filters doesn't break admin dashboard dropdown.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getAvailableCombinations();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/available-combinations",
      {}
    );
  });

  // ─── getStudents ──────────────────────────────────────────────────

  it("getStudents passes 3 required query params + spreads college_code when provided", async () => {
    // Pin: college_code is OPTIONAL — spread via conditional
    // object. Pin so refactor sending college_code: undefined
    // doesn't change backend Pydantic validation behavior.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getStudents(7, 114, "first", "A");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/students",
      {
        params: {
          query: {
            scholarship_type_id: 7,
            academic_year: 114,
            semester: "first",
            college_code: "A",
          },
        },
      }
    );
  });

  it("getStudents omits college_code when undefined", async () => {
    // Pin: omitted (NOT undefined). Pin so refactor doesn't send
    // college_code: undefined which some backends treat as "all
    // colleges except none".
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getStudents(7, 114, "first");
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect("college_code" in query).toBe(false);
  });

  // ─── getQuotaStatus ───────────────────────────────────────────────

  it("getQuotaStatus GETs /quota-status with 3 required params", async () => {
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getQuotaStatus(7, 114, "first");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/quota-status",
      {
        params: {
          query: {
            scholarship_type_id: 7,
            academic_year: 114,
            semester: "first",
          },
        },
      }
    );
  });

  // ─── allocate ─────────────────────────────────────────────────────

  it("allocate POSTs /allocate with full AllocateRequest body", async () => {
    // Pin SECURITY: full body propagated as-is — allocations
    // array drives WHO gets WHICH sub_type for WHICH config pool. Drift
    // would silently misallocate funds.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.allocate({
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
      allocations: [
        { ranking_item_id: 1, sub_type_code: "nstc", allocation_config_id: 42 },
        { ranking_item_id: 2, sub_type_code: null, allocation_config_id: null },
      ],
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/allocate",
      {
        body: {
          scholarship_type_id: 7,
          academic_year: 114,
          semester: "first",
          allocations: [
            { ranking_item_id: 1, sub_type_code: "nstc", allocation_config_id: 42 },
            { ranking_item_id: 2, sub_type_code: null, allocation_config_id: null },
          ],
        },
      }
    );
  });

  // ─── finalize ─────────────────────────────────────────────────────

  it("finalize POSTs /finalize with FinalizeRequest body", async () => {
    // Pin: finalize LOCKS allocations and updates application
    // statuses. SECURITY-critical — pin so refactor adding extra
    // fields doesn't expand the locking scope unexpectedly.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.finalize({
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/finalize",
      {
        body: {
          scholarship_type_id: 7,
          academic_year: 114,
          semester: "first",
        },
      }
    );
  });

  // ─── getHistory (path-templated scholarship_type_id) ──────────────

  it("getHistory uses typed-route path param for scholarship_type_id", async () => {
    // Pin: scholarship_type_id is in PATH (not query) for history.
    // Uses openapi-fetch typed-route form: literal {scholarship_type_id}
    // in the URL string, real value via params.path. Pin so refactor
    // moving it to query breaks the admin history view.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getHistory(7, 114, "first");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/{scholarship_type_id}/history",
      {
        params: {
          path: { scholarship_type_id: 7 },
          query: { academic_year: 114, semester: "first" },
        },
      }
    );
  });

  // ─── restoreFromHistory ───────────────────────────────────────────

  it("restoreFromHistory POSTs typed-route /{id}/restore with history_id body", async () => {
    // Pin SECURITY: restore replays a historical allocation —
    // typed-route scholarship_type_id in params.path + body with
    // history_id. Pin so refactor doesn't mismatch scholarship vs. history.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.restoreFromHistory(7, { history_id: 42 });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/{scholarship_type_id}/restore",
      {
        params: { path: { scholarship_type_id: 7 } },
        body: { history_id: 42 },
      }
    );
  });

  // ─── getDistributionSummary ───────────────────────────────────────

  it("getDistributionSummary GETs /distribution-summary with 3 params", async () => {
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getDistributionSummary(7, 114, "first");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/distribution-summary",
      {
        params: {
          query: {
            scholarship_type_id: 7,
            academic_year: 114,
            semester: "first",
          },
        },
      }
    );
  });

  // ─── getAutoAllocatePreview ───────────────────────────────────────

  it("getAutoAllocatePreview omits college_code and staged when not supplied", async () => {
    // POST carries the staged overlay in a body, but still writes nothing —
    // a refactor must not turn it into a destructive call.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getAutoAllocatePreview(7, 114, "first");
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/auto-allocate-preview",
      {
        body: {
          scholarship_type_id: 7,
          academic_year: 114,
          semester: "first",
        },
      }
    );
  });

  it("getAutoAllocatePreview spreads college_code for a single-college run", async () => {
    // Pin: the per-college 預設分發 button scopes the preview to one
    // college. The field must only appear when supplied — an empty
    // string would narrow the whole-scholarship run to nothing.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getAutoAllocatePreview(7, 114, "first", "C");
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/auto-allocate-preview",
      {
        body: {
          scholarship_type_id: 7,
          academic_year: 114,
          semester: "first",
          college_code: "C",
        },
      }
    );
  });

  it("getAutoAllocatePreview sends an EMPTY overlay rather than dropping it", async () => {
    // `[]` is truthy in JS and falsy in Python, so a truthiness guard here
    // would ship "no rows are allocated" and have the server read "no overlay
    // given" — silently planning against the SAVED distribution instead.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getAutoAllocatePreview(7, 114, "first", undefined, []);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/auto-allocate-preview",
      {
        body: {
          scholarship_type_id: 7,
          academic_year: 114,
          semester: "first",
          staged: [],
        },
      }
    );
  });

  it("getAutoAllocatePreview sends the staged overlay so the plan follows the screen", async () => {
    // Pin: without this the server plans against the SAVED distribution, and a
    // slot the admin just unticked stays invisible to it.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    const staged = [
      { ranking_item_id: 1, sub_type_code: null, allocation_config_id: null },
      { ranking_item_id: 2, sub_type_code: "nstc", allocation_config_id: 115 },
    ];
    await api.getAutoAllocatePreview(7, 114, "first", "C", staged);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/auto-allocate-preview",
      {
        body: {
          scholarship_type_id: 7,
          academic_year: 114,
          semester: "first",
          college_code: "C",
          staged,
        },
      }
    );
  });

  // ─── generateRostersFromDistribution ──────────────────────────────

  it("generateRostersFromDistribution POSTs with optional flags", async () => {
    // Pin: optional flags (student_verification_enabled,
    // force_regenerate) preserved as-is. SECURITY: explicit false
    // must NOT be dropped — pin so refactor doesn't strip
    // explicit false.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.generateRostersFromDistribution({
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
      student_verification_enabled: false,
      force_regenerate: false,
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/generate-rosters-from-distribution",
      {
        body: {
          scholarship_type_id: 7,
          academic_year: 114,
          semester: "first",
          student_verification_enabled: false,
          force_regenerate: false,
        },
      }
    );
  });

  // ─── revokeAllocation ────────────────────────────────────────────

  it("revokeAllocation POSTs reason to the revoke endpoint", async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: "已撤銷", data: {} }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;
    const api = createManualDistributionApi();

    const res = await api.revokeAllocation(42, "申請人撤回");

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/applications/42/revoke",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ reason: "申請人撤回" }),
      })
    );
    expect(res.success).toBe(true);
  });

  // ─── suspendAllocation ────────────────────────────────────────────

  it("suspendAllocation POSTs reason to the suspend endpoint", async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: "已停發", data: {} }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;
    const api = createManualDistributionApi();

    const res = await api.suspendAllocation(42, "休學：已辦理 114-2 休學");

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/applications/42/suspend",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ reason: "休學：已辦理 114-2 休學" }),
      })
    );
    expect(res.success).toBe(true);
  });

  // ─── 15-method invariant ──────────────────────────────────────────

  it("module exposes exactly 15 methods", async () => {
    // Pin: 15 methods. Pin so refactor adding/removing methods
    // requires explicit review (each one drives a SECURITY-
    // critical allocation operation).
    const api = createManualDistributionApi();
    expect(Object.keys(api).sort()).toEqual([
      "allocate",
      "finalize",
      "generateRostersFromDistribution",
      "getAutoAllocatePreview",
      "getAvailableCombinations",
      "getDistributionSummary",
      "getHistory",
      "getQuotaStatus",
      "getState",
      "getStudents",
      "previewDistribution",
      "restoreAllocation",
      "restoreFromHistory",
      "revokeAllocation",
      "suspendAllocation",
    ]);
  });

  it("restoreAllocation POSTs to the restore endpoint", async () => {
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: "已恢復", data: {} }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;
    const api = createManualDistributionApi();

    const res = await api.restoreAllocation(42);

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/applications/42/restore",
      expect.objectContaining({ method: "POST" })
    );
    expect(res.success).toBe(true);
  });
});

// ─── mergeSuggestions ─────────────────────────────────────────────────
//
// The staging rules shared by the on-load auto-preview and the 預設分發
// buttons. What these stage is what 儲存 persists — but the quota cap now
// lives server-side, where the suggestions are computed against this same
// staged map (see getAutoAllocatePreview's `staged`).

describe("mergeSuggestions", () => {
  const suggestion = (
    ranking_item_id: number,
    sub_type_code: string | null = "nstc",
    allocation_config_id: number | null = 115
  ) => ({ ranking_item_id, sub_type_code, allocation_config_id });

  it("fills only eligible 未決 rows and never mutates the input map", () => {
    const current = new Map([[2, { sub_type: "moe_1w", config_id: 115 }]]);
    const res = mergeSuggestions(
      current,
      [suggestion(1), suggestion(2), suggestion(3)],
      new Set([1, 2]) // 3 is not in the grid / not this college
    );
    expect(res.filled).toBe(1);
    expect(res.next.get(1)).toEqual({ sub_type: "nstc", config_id: 115 });
    // 2 keeps the admin's hand-picked value; 3 was never eligible.
    expect(res.next.get(2)).toEqual({ sub_type: "moe_1w", config_id: 115 });
    expect(res.next.has(3)).toBe(false);
    expect(current.size).toBe(1);
  });

  it("skips suggestions with no sub_type or no config (unallocatable rows)", () => {
    const res = mergeSuggestions(
      new Map(),
      [suggestion(1, null, null), suggestion(2, "nstc", null)],
      new Set([1, 2])
    );
    expect(res.filled).toBe(0);
    expect(res.next.size).toBe(0);
  });

  it("fills a row that is present-but-null — 未決 is not 'decided'", () => {
    // An unticked row and a never-touched row are both 未決. The server was
    // told so and planned for it, so the merge must not second-guess it.
    const res = mergeSuggestions(
      new Map([[1, null]]),
      [suggestion(1)],
      new Set([1])
    );
    expect(res.filled).toBe(1);
    expect(res.next.get(1)).toEqual({ sub_type: "nstc", config_id: 115 });
  });

  it("applies every suggestion it is given — no client-side quota cap", () => {
    // The server allocated these against the staged map it was sent, so a
    // second cap here could only drop a row it deliberately allocated.
    const res = mergeSuggestions(
      new Map(),
      [suggestion(1), suggestion(2), suggestion(3)],
      new Set([1, 2, 3])
    );
    expect(res.filled).toBe(3);
  });
});

describe("toStagedItems", () => {
  it("sends every row, 未決 ones as explicit nulls", () => {
    // The overlay must be complete: a row it omits falls back to the SAVED
    // state server-side, which is exactly the bug this replaced.
    expect(
      toStagedItems(
        new Map([
          [1, { sub_type: "nstc", config_id: 115 }],
          [2, null],
        ])
      )
    ).toEqual([
      { ranking_item_id: 1, sub_type_code: "nstc", allocation_config_id: 115 },
      { ranking_item_id: 2, sub_type_code: null, allocation_config_id: null },
    ]);
  });
});

describe("isCancelledAllocation", () => {
  const s = (quota_allocation_status: string | null) =>
    ({ quota_allocation_status }) as never;

  it("is true only for 撤銷/停發", () => {
    expect(isCancelledAllocation(s("revoked"))).toBe(true);
    expect(isCancelledAllocation(s("suspended"))).toBe(true);
    expect(isCancelledAllocation(s("allocated"))).toBe(false);
    expect(isCancelledAllocation(s("rejected"))).toBe(false);
    expect(isCancelledAllocation(s(null))).toBe(false);
  });
});

describe("reasonsBySuggestion / summarizeReasons", () => {
  const s = (
    ranking_item_id: number,
    sub_type_code: string | null,
    reason?: string | null
  ) =>
    ({
      ranking_item_id,
      sub_type_code,
      allocation_config_id: sub_type_code ? 115 : null,
      reason,
    }) as never;

  it("keeps only the rows the run could not place", () => {
    const reasons = reasonsBySuggestion([
      s(1, "nstc", null),
      s(2, null, "quota_full"),
      s(3, null, "review_rejected"),
    ]);
    expect(reasons.get(1)).toBeUndefined();
    expect(reasons.get(2)).toBe("quota_full");
    expect(reasons.get(3)).toBe("review_rejected");
  });

  it("ignores an unplaced row with no reason rather than inventing one", () => {
    // The frontend must never guess: a reject from a reviewer role the grid
    // does not render looks identical to an exhausted quota from here.
    expect(reasonsBySuggestion([s(1, null, null)]).size).toBe(0);
  });

  it("tallies reasons, most common first", () => {
    const reasons = reasonsBySuggestion([
      s(1, null, "review_rejected"),
      s(2, null, "review_rejected"),
      s(3, null, "quota_full"),
    ]);
    expect(summarizeReasons(reasons)).toEqual([
      { reason: "review_rejected", count: 2 },
      { reason: "quota_full", count: 1 },
    ]);
  });

  it("drops 撤銷/停發 rows — they were never candidates", () => {
    // They render their own status control, and counting them would report a
    // dozen "failures" for a college where nothing actually went wrong.
    expect(reasonsBySuggestion([s(1, null, "cancelled")]).size).toBe(0);
  });

  it("labels every reason the backend can emit", () => {
    // Pin: the union mirrors the UNALLOCATED_* constants in
    // manual_distribution_service.py — a new code must land in both.
    expect(Object.keys(UNALLOCATED_REASON_LABEL).sort()).toEqual([
      "cancelled",
      "college_rejected",
      "no_college_quota",
      "not_applied",
      "quota_full",
      "review_rejected",
    ]);
  });

  it("falls back to the raw code for a reason this build has not learnt", () => {
    // The union is hand-kept and the response is untyped, so a backend that
    // ships a new code first must not render 「未分配: undefined」.
    expect(unallocatedReasonLabel("quota_full")).toBe("名額不足");
    expect(
      unallocatedReasonLabel("brand_new_code" as UnallocatedReason)
    ).toBe("brand_new_code");
  });
});

// ─── Binary export (shared fetchBinaryExport) ──────────────────────

describe("exportDistributionSummary", () => {
  const okResponse = (disposition: string) => ({
    ok: true,
    headers: { get: jest.fn().mockReturnValue(disposition) },
    blob: jest.fn().mockResolvedValue(new Blob(["xlsx"])),
  });

  it("sends the three selection params, Bearer auth, and decodes filename*", async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValue(
        okResponse("attachment; filename*=UTF-8''%E5%88%86%E7%99%BC%E5%90%8D%E5%96%AE.xlsx")
      );
    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await exportDistributionSummary({
      scholarshipTypeId: 7,
      academicYear: 114,
      semester: "yearly",
    });

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain(
      "/api/v1/manual-distribution/distribution-summary/export"
    );
    expect(url).toContain("scholarship_type_id=7");
    expect(url).toContain("academic_year=114");
    expect(url).toContain("semester=yearly");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe(
      "Bearer test-token"
    );
    expect(result.filename).toBe("分發名單.xlsx");
  });

  it("omits format for xlsx (URL unchanged) and appends it for pdf", async () => {
    const fetchMock = jest.fn().mockResolvedValue(okResponse(""));
    global.fetch = fetchMock as unknown as typeof fetch;

    await exportDistributionSummary({
      scholarshipTypeId: 7,
      academicYear: 114,
      semester: "first",
    });
    expect(fetchMock.mock.calls[0][0]).not.toContain("format=");

    await exportDistributionSummary({
      scholarshipTypeId: 7,
      academicYear: 114,
      semester: "first",
      format: "pdf",
    });
    expect(fetchMock.mock.calls[1][0]).toContain("format=pdf");
  });

  it("falls back to 分發名單_{year}.{ext} without Content-Disposition", async () => {
    const fetchMock = jest.fn().mockResolvedValue(okResponse(""));
    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await exportDistributionSummary({
      scholarshipTypeId: 7,
      academicYear: 114,
      semester: "yearly",
      format: "pdf",
    });
    expect(result.filename).toBe("分發名單_114.pdf");
  });

  it("surfaces the backend message on a non-OK response", async () => {
    // The 404 branches (尚未完成分發 / 尚無已分配的學生) must reach the toast,
    // not the generic fallback.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      json: jest.fn().mockResolvedValue({ message: "尚未完成分發，無法匯出" }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(
      exportDistributionSummary({
        scholarshipTypeId: 7,
        academicYear: 114,
        semester: "yearly",
      })
    ).rejects.toThrow("尚未完成分發，無法匯出");
  });

  it("falls back to zh-TW when the error body is unparseable", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      json: jest.fn().mockRejectedValue(new Error("no JSON")),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(
      exportDistributionSummary({
        scholarshipTypeId: 7,
        academicYear: 114,
        semester: "yearly",
      })
    ).rejects.toThrow("無法匯出分發名單");
  });
});
