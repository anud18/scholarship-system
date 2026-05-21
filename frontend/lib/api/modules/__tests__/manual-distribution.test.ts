/**
 * Tests for `frontend/lib/api/modules/manual-distribution.ts`.
 *
 * Module had ZERO dedicated test coverage. SECURITY-CRITICAL —
 * controls scholarship allocation (who gets paid, how much, and
 * for which year/sub-type). Drift in body shape or path templating
 * would silently misallocate funds.
 *
 * Wave 6a135 pins the 12 methods: URL paths, body shapes, path-
 * templated history/restore, query-spread of optional college_code,
 * and the raw-fetch import-received-months path (URLSearchParams +
 * Bearer + error fallback chain).
 *
 * 16 cases.
 */

import { createManualDistributionApi } from "../manual-distribution";
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
    // array drives WHO gets WHICH sub_type for WHICH year. Drift
    // would silently misallocate funds.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.allocate({
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
      allocations: [
        { ranking_item_id: 1, sub_type_code: "nstc", allocation_year: 114 },
        { ranking_item_id: 2, sub_type_code: null, allocation_year: null },
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
            { ranking_item_id: 1, sub_type_code: "nstc", allocation_year: 114 },
            { ranking_item_id: 2, sub_type_code: null, allocation_year: null },
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

  it("getAutoAllocatePreview GETs /auto-allocate-preview (preview only, no DB writes)", async () => {
    // Pin: preview endpoint — server returns suggestions WITHOUT
    // mutating allocations. Pin so refactor doesn't accidentally
    // change it to a destructive POST.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createManualDistributionApi();
    await api.getAutoAllocatePreview(7, 114, "first");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/auto-allocate-preview",
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

  // ─── importReceivedMonths (raw fetch, FormData + URLSearchParams) ─

  it("importReceivedMonths uses raw fetch with URLSearchParams + Bearer + FormData", async () => {
    // Pin: bypasses typedClient because multipart upload with
    // URL-encoded query string. Bearer token from typedClient.getToken().
    const fakeFile = new File(["xlsx-bytes"], "received.xlsx");
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: jest.fn().mockResolvedValue({
        success: true,
        message: "",
        data: { matched: 5, not_found: [], updated: 5 },
      }),
    });
    global.fetch = fetchMock as any;

    const api = createManualDistributionApi();
    await api.importReceivedMonths(7, 114, "first", fakeFile);

    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe(
      "/api/v1/manual-distribution/import-received-months?scholarship_type_id=7&academic_year=114&semester=first"
    );
    expect(opts.method).toBe("POST");
    expect(opts.headers.Authorization).toBe("Bearer test-token");
    expect(opts.body).toBeInstanceOf(FormData);
  });

  it("importReceivedMonths omits Authorization header when no token", async () => {
    // Pin: when getToken() returns null/undefined, Authorization
    // header is OMITTED entirely (NOT "Bearer null"). Pin
    // because backend distinguishes missing token (401) vs
    // malformed token (400) and we want the cleaner 401.
    (typedClient.getToken as jest.Mock).mockReturnValueOnce(null);
    const fakeFile = new File(["x"], "x.xlsx");
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: jest.fn().mockResolvedValue({ success: true, data: {} }),
    });
    global.fetch = fetchMock as any;

    const api = createManualDistributionApi();
    await api.importReceivedMonths(7, 114, "first", fakeFile);

    const opts = fetchMock.mock.calls[0][1];
    expect("Authorization" in opts.headers).toBe(false);
  });

  it("importReceivedMonths surfaces backend message on non-OK", async () => {
    // Pin: error fallback chain — prefer body.message, then
    // body.detail, then HTTP-status fallback.
    const fakeFile = new File(["x"], "x.xlsx");
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: jest.fn().mockResolvedValue({ message: "duplicate student ID" }),
    });
    global.fetch = fetchMock as any;

    const api = createManualDistributionApi();
    const result = await api.importReceivedMonths(7, 114, "first", fakeFile);

    expect(result.success).toBe(false);
    expect(result.message).toBe("duplicate student ID");
  });

  it("importReceivedMonths falls back to body.detail when no message", async () => {
    const fakeFile = new File(["x"], "x.xlsx");
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: jest.fn().mockResolvedValue({ detail: "internal error" }),
    });
    global.fetch = fetchMock as any;

    const api = createManualDistributionApi();
    const result = await api.importReceivedMonths(7, 114, "first", fakeFile);

    expect(result.success).toBe(false);
    expect(result.message).toBe("internal error");
  });

  it("importReceivedMonths uses HTTP-status fallback when body unparseable", async () => {
    // Pin: when JSON parsing throws (non-JSON response body),
    // fall back to "Upload failed (HTTP {status})". Pin so
    // refactor doesn't silently mask the failure with a generic
    // message.
    const fakeFile = new File(["x"], "x.xlsx");
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: jest.fn().mockRejectedValue(new Error("not JSON")),
    });
    global.fetch = fetchMock as any;

    const api = createManualDistributionApi();
    const result = await api.importReceivedMonths(7, 114, "first", fakeFile);

    expect(result.success).toBe(false);
    expect(result.message).toBe("Upload failed (HTTP 502)");
  });

  // ─── 11-method invariant ──────────────────────────────────────────

  it("module exposes exactly 13 methods", async () => {
    // Pin: 13 methods. Pin so refactor adding/removing methods
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
      "getStudents",
      "importReceivedMonths",
      "restoreFromHistory",
      "revoke",
      "suspend",
    ]);
  });
});
