/**
 * Tests for `frontend/lib/api/modules/college.ts`.
 *
 * Module had ZERO dedicated test coverage. 636 LOC, 22 instance
 * methods + 3 module-level export helpers. SECURITY-CRITICAL —
 * drives college-level scholarship review, ranking management,
 * and distribution execution.
 *
 * Wave 6a137 pins the dispatch invariants — URL paths, body
 * shapes, default-value preservation (force_new ?? false),
 * legacy-vs-unified review path distinction, and the binary-
 * export Content-Disposition filename extraction + error
 * fallback chain in _fetchBinaryExport.
 *
 * 24 cases.
 */

import {
  createCollegeApi,
  exportRankingExcel,
  exportDepartmentSummary,
  exportDepartmentSummaryBulk,
  downloadRankingTemplate,
} from "../college";
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

jest.mock("../../compat", () => ({
  toApiResponse: jest.fn((r) => r),
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

describe("createCollegeApi", () => {
  // ─── getApplicationsForReview URLSearchParams parsing ─────────────

  it("getApplicationsForReview parses academic_year to int, others passthrough", async () => {
    // Pin: only academic_year is coerced (parseInt). semester and
    // scholarship_type stay strings. Pin so refactor doesn't
    // silently coerce strings that are valid numbers (e.g.,
    // semester "1" → integer).
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.getApplicationsForReview(
      "academic_year=114&semester=first&scholarship_type=nstc"
    );
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/college-review/applications",
      {
        params: {
          query: {
            academic_year: 114,
            semester: "first",
            scholarship_type: "nstc",
          },
        },
      }
    );
  });

  it("getApplicationsForReview emits empty query object when no string passed", async () => {
    // Pin: undefined queryString → empty object (NOT undefined).
    // Pin so refactor doesn't break backend Pydantic which expects
    // a dict.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.getApplicationsForReview();
    expect(mockedRaw.GET.mock.calls[0][1].params.query).toEqual({});
  });

  it("getApplicationsForReview skips keys when value is empty string", async () => {
    // Pin: URLSearchParams keys with empty values are SKIPPED, not
    // forwarded as empty strings. Pin so refactor doesn't send
    // `semester=""` which backend may interpret differently.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.getApplicationsForReview("academic_year=&semester=&scholarship_type=");
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query).toEqual({});
  });

  // ─── createRanking default + force_new ?? false ───────────────────

  it("createRanking defaults force_new=false when undefined", async () => {
    // Pin SECURITY: force_new defaults to FALSE — server-side guard
    // against accidentally creating duplicate ranking. Use `??`
    // (NOT `||`) so explicit-false stays false. Pin so refactor
    // doesn't flip default to true.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.createRanking({
      ranking_name: "114年一上初評排名",
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
    } as any);
    expect(mockedRaw.POST.mock.calls[0][1].body.force_new).toBe(false);
  });

  it("createRanking preserves force_new=true when explicit", async () => {
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.createRanking({
      ranking_name: "regen",
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
      force_new: true,
    } as any);
    expect(mockedRaw.POST.mock.calls[0][1].body.force_new).toBe(true);
  });

  // ─── updateRanking / updateRankingOrder body distinction ──────────

  it("updateRanking PUTs /{ranking_id} with ranking_name-only body", async () => {
    // Pin: NAME-only update — body is {ranking_name}. Pin so
    // refactor adding more fields to this endpoint doesn't break
    // the admin rename dialog.
    mockedRaw.PUT.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.updateRanking(42, { ranking_name: "新名稱" });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/college-review/rankings/{ranking_id}",
      { params: { path: { ranking_id: 42 } }, body: { ranking_name: "新名稱" } }
    );
  });

  it("updateRankingOrder body is ARRAY (NOT wrapped object)", async () => {
    // Pin SECURITY: body is bare Array<{item_id, position}> — pin
    // so refactor wrapping in {items: [...]} would break backend
    // FastAPI Body parser and silently reorder NOTHING.
    mockedRaw.PUT.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.updateRankingOrder(42, [
      { item_id: 1, position: 1 },
      { item_id: 2, position: 2 },
    ]);
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/college-review/rankings/{ranking_id}/order",
      {
        params: { path: { ranking_id: 42 } },
        body: [
          { item_id: 1, position: 1 },
          { item_id: 2, position: 2 },
        ],
      }
    );
  });

  // ─── finalize / unfinalize distinct paths ─────────────────────────

  it("finalizeRanking and unfinalizeRanking hit DISTINCT paths (both POST, no body)", async () => {
    // Pin: distinct paths — pin so refactor consolidating into a
    // single toggle PATCH with body doesn't break the locking
    // semantics admin UI relies on.
    mockedRaw.POST.mockResolvedValue({});
    const api = createCollegeApi();
    await api.finalizeRanking(42);
    await api.unfinalizeRanking(42);
    expect(mockedRaw.POST.mock.calls[0][0]).toBe(
      "/api/v1/college-review/rankings/{ranking_id}/finalize"
    );
    expect(mockedRaw.POST.mock.calls[1][0]).toBe(
      "/api/v1/college-review/rankings/{ranking_id}/unfinalize"
    );
  });

  // ─── importRankingExcel body is array ─────────────────────────────

  it("importRankingExcel body is ARRAY of {student_id, student_name, rank_position}", async () => {
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.importRankingExcel(42, [
      { student_id: "310460031", student_name: "王小明", rank_position: 1 },
      { student_id: "310460032", student_name: "李大華", rank_position: 2 },
    ]);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/college-review/rankings/{ranking_id}/import-excel",
      expect.objectContaining({
        body: expect.arrayContaining([
          expect.objectContaining({ student_id: "310460031" }),
        ]),
      })
    );
  });

  // ─── deleteRanking ────────────────────────────────────────────────

  it("deleteRanking DELETEs path-templated /{ranking_id}", async () => {
    mockedRaw.DELETE.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.deleteRanking(42);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/college-review/rankings/{ranking_id}",
      { params: { path: { ranking_id: 42 } } }
    );
  });

  // ─── getQuotaStatus + optional semester ───────────────────────────

  it("getQuotaStatus passes semester even when undefined (NOT omitted)", async () => {
    // Pin: semester is included with `undefined` value (NOT
    // omitted via spread). Backend Pydantic accepts `semester:
    // null` for yearly scholarships. Pin so refactor adding spread
    // doesn't break yearly-scholarship quota lookup.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.getQuotaStatus(7, 114);
    expect(mockedRaw.GET.mock.calls[0][1].params.query).toEqual({
      scholarship_type_id: 7,
      academic_year: 114,
      semester: undefined,
    });
  });

  // ─── reviewApplication (legacy) vs submitReview (unified) ─────────

  it("reviewApplication POSTs legacy /college-review/applications/{id}/review", async () => {
    // Pin SCOPE: this is the LEGACY college-review-only endpoint
    // (NOT the unified multi-role /reviews/* path). Pin so refactor
    // doesn't collapse with submitReview — they have different
    // backend handlers and body schemas.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.reviewApplication(42, {
      recommendation: "approve",
      review_comments: "good candidate",
    });
    expect(mockedRaw.POST.mock.calls[0][0]).toBe(
      "/api/v1/college-review/applications/{application_id}/review"
    );
  });

  it("submitReview POSTs unified /reviews/applications/{id}/review (multi-role)", async () => {
    // Pin: unified multi-role review system — body has `items`
    // array with per-sub_type recommendations. Distinct from
    // legacy reviewApplication.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.submitReview(42, {
      items: [
        { sub_type_code: "nstc", recommendation: "approve" },
        { sub_type_code: "moe_1w", recommendation: "reject", comments: "..." },
      ],
    });
    expect(mockedRaw.POST.mock.calls[0][0]).toBe(
      "/api/v1/reviews/applications/{application_id}/review"
    );
    expect(mockedRaw.POST.mock.calls[0][1].body.items).toHaveLength(2);
  });

  it("getSubTypes + getReview use unified /reviews/* (NOT /college-review/*)", async () => {
    // Pin: unified endpoints — pin so refactor moving them under
    // /college-review/* breaks professor/admin reviewers.
    mockedRaw.GET.mockResolvedValue({});
    const api = createCollegeApi();
    await api.getSubTypes(42);
    await api.getReview(42);
    expect(mockedRaw.GET.mock.calls[0][0]).toBe(
      "/api/v1/reviews/applications/{application_id}/sub-types"
    );
    expect(mockedRaw.GET.mock.calls[1][0]).toBe(
      "/api/v1/reviews/applications/{application_id}/review"
    );
  });

  // ─── Enumeration / preview endpoints ──────────────────────────────

  it("getAvailableCombinations GETs /available-combinations with empty options", async () => {
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.getAvailableCombinations();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/college-review/available-combinations",
      {}
    );
  });

  it("getManagedCollege + getSubTypeTranslations GET with empty options", async () => {
    mockedRaw.GET.mockResolvedValue({});
    const api = createCollegeApi();
    await api.getManagedCollege();
    await api.getSubTypeTranslations();
    expect(mockedRaw.GET.mock.calls[0][0]).toBe(
      "/api/v1/college-review/managed-college"
    );
    expect(mockedRaw.GET.mock.calls[1][0]).toBe(
      "/api/v1/college-review/sub-type-translations"
    );
  });

  it("getStudentPreview templates student_id path + optional academic_year query", async () => {
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createCollegeApi();
    await api.getStudentPreview("310460031", 114);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/college-review/students/{student_id}/preview",
      {
        params: {
          path: { student_id: "310460031" },
          query: { academic_year: 114 },
        },
      }
    );
  });

  // ─── exportPackage (raw fetch + URLSearchParams + token in URL) ───

  it("exportPackage sends token via QUERY (NOT Authorization header)", async () => {
    // Pin SECURITY: token in QUERY for download links (so direct
    // browser navigation works). Pin so refactor moving to header
    // breaks "right-click → save as" download UX.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: {
        get: jest.fn().mockReturnValue(
          "attachment; filename*=UTF-8''%E5%8C%85.zip"
        ),
      },
      blob: jest.fn().mockResolvedValue(new Blob(["zip"])),
    });
    global.fetch = fetchMock as any;

    const api = createCollegeApi();
    const result = await api.exportPackage({
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
      token: "abc-token",
    });
    const url = fetchMock.mock.calls[0][0];
    expect(url).toContain("scholarship_type_id=7");
    expect(url).toContain("academic_year=114");
    expect(url).toContain("semester=first");
    expect(url).toContain("token=abc-token");
    expect(result.filename).toBe("包.zip");
  });

  it("exportPackage omits semester from query when not provided", async () => {
    // Pin: optional semester — pin so yearly scholarships export
    // doesn't accidentally include `semester=` empty string.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: { get: jest.fn().mockReturnValue("") },
      blob: jest.fn().mockResolvedValue(new Blob()),
    });
    global.fetch = fetchMock as any;

    const api = createCollegeApi();
    await api.exportPackage({
      scholarship_type_id: 7,
      academic_year: 114,
      token: "abc",
    });
    expect(fetchMock.mock.calls[0][0]).not.toContain("semester=");
  });

  it("exportPackage throws on non-OK with backend error fallback chain", async () => {
    // Pin: error → backend `error` first, then `detail`, then
    // fallback "匯出失敗" zh-TW.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      json: jest.fn().mockResolvedValue({ error: "permission denied" }),
    });
    global.fetch = fetchMock as any;

    const api = createCollegeApi();
    await expect(
      api.exportPackage({
        scholarship_type_id: 7,
        academic_year: 114,
        token: "abc",
      })
    ).rejects.toThrow("permission denied");
  });

  it("exportPackage uses zh-TW fallback when no error body", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      json: jest.fn().mockRejectedValue(new Error("no JSON")),
    });
    global.fetch = fetchMock as any;

    const api = createCollegeApi();
    await expect(
      api.exportPackage({
        scholarship_type_id: 7,
        academic_year: 114,
        token: "abc",
      })
    ).rejects.toThrow("匯出失敗");
  });
});

// ─── Module-level export helpers (use shared _fetchBinaryExport) ────

describe("module-level export helpers", () => {
  it("exportRankingExcel uses Bearer header + extracts filename* UTF-8 encoded", async () => {
    // Pin: Bearer from typedClient.getToken(). filename extraction
    // via `filename*=UTF-8''<encoded>` regex with URL-decode.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: {
        get: jest.fn().mockReturnValue(
          "attachment; filename*=UTF-8''%E5%AD%B8%E7%94%9F.xlsx"
        ),
      },
      blob: jest.fn().mockResolvedValue(new Blob(["xlsx"])),
    });
    global.fetch = fetchMock as any;

    const result = await exportRankingExcel(42);
    expect(result.filename).toBe("學生.xlsx");
    const headers = fetchMock.mock.calls[0][1].headers;
    expect(headers.Authorization).toBe("Bearer test-token");
  });

  it("exportRankingExcel falls back to '學生資料彙整表_{id}.xlsx' when no Content-Disposition", async () => {
    // Pin: fallback filename includes the ranking ID for
    // disambiguation. Pin so refactor doesn't lose the ID in the
    // fallback.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: { get: jest.fn().mockReturnValue("") },
      blob: jest.fn().mockResolvedValue(new Blob()),
    });
    global.fetch = fetchMock as any;

    const result = await exportRankingExcel(42);
    expect(result.filename).toBe("學生資料彙整表_42.xlsx");
  });

  it("exportRankingExcel(format='pdf') adds ?format=pdf and .pdf fallback", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: { get: jest.fn().mockReturnValue("") },
      blob: jest.fn().mockResolvedValue(new Blob()),
    });
    global.fetch = fetchMock as any;

    const result = await exportRankingExcel(42, "pdf");
    expect(fetchMock.mock.calls[0][0]).toContain("format=pdf");
    expect(result.filename).toBe("學生資料彙整表_42.pdf");
  });

  it("exportRankingExcel(format='xlsx') omits the format param (URL unchanged)", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: { get: jest.fn().mockReturnValue("") },
      blob: jest.fn().mockResolvedValue(new Blob()),
    });
    global.fetch = fetchMock as any;

    await exportRankingExcel(42, "xlsx");
    expect(fetchMock.mock.calls[0][0]).not.toContain("format=");
  });

  it("exportDepartmentSummary URL includes 4 params + dept_code", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: { get: jest.fn().mockReturnValue("") },
      blob: jest.fn().mockResolvedValue(new Blob()),
    });
    global.fetch = fetchMock as any;

    await exportDepartmentSummary({
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
      department_code: "4460",
    });
    const url = fetchMock.mock.calls[0][0];
    expect(url).toContain("scholarship_type_id=7");
    expect(url).toContain("academic_year=114");
    expect(url).toContain("semester=first");
    expect(url).toContain("department_code=4460");
  });

  it("exportDepartmentSummaryBulk includes scope and uses fallback ZIP filename", async () => {
    // Pin: scope='college' vs 'all' is REQUIRED — distinguishes
    // managed-college-only bulk vs all-colleges bulk. Fallback
    // filename is "申請總表.zip" (NOT .xlsx).
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: { get: jest.fn().mockReturnValue("") },
      blob: jest.fn().mockResolvedValue(new Blob()),
    });
    global.fetch = fetchMock as any;

    const result = await exportDepartmentSummaryBulk({
      scholarship_type_id: 7,
      academic_year: 114,
      scope: "college",
    });
    const url = fetchMock.mock.calls[0][0];
    expect(url).toContain("scope=college");
    expect(result.filename).toBe("申請總表.zip");
  });

  it("_fetchBinaryExport (via exportRankingExcel) propagates backend detail on non-OK", async () => {
    // Pin: error fallback chain — body.detail → body.message →
    // body.error → fallback "無法匯出排名資料".
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      json: jest.fn().mockResolvedValue({ detail: "no permission" }),
    });
    global.fetch = fetchMock as any;

    await expect(exportRankingExcel(42)).rejects.toThrow("no permission");
  });

  it("_fetchBinaryExport falls back to zh-TW when backend body unparseable", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      json: jest.fn().mockRejectedValue(new Error("no JSON")),
    });
    global.fetch = fetchMock as any;

    await expect(exportRankingExcel(42)).rejects.toThrow("無法匯出排名資料");
  });

  it("downloadRankingTemplate hits export-excel with template=true + 範本 fallback filename", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: { get: jest.fn().mockReturnValue("") },
      blob: jest.fn().mockResolvedValue(new Blob()),
    });
    global.fetch = fetchMock as any;

    const result = await downloadRankingTemplate(42);

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/rankings/42/export-excel");
    expect(url).toContain("template=true");
    expect(result.filename).toBe("學生資料彙整表_42_範本.xlsx");
  });
});
