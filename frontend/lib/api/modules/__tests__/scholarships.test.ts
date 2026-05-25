/**
 * Tests for `frontend/lib/api/modules/scholarships.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the student
 * scholarship-listing UI (eligible scholarships, detail) plus
 * admin combined-PhD creation flow.
 *
 * Wave 6a120 pins URL paths + the combined-PhD body shape
 * including the sub_type enum allowlist ("nstc" | "moe") — pin
 * so a refactor to add a 3rd sub_type silently breaks backend
 * Pydantic validation.
 *
 * 9 cases.
 */

import { createScholarshipsApi } from "../scholarships";
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

describe("createScholarshipsApi", () => {
  // ─── getEligible ────────────────────────────────────────────────────

  it("getEligible GETs /api/v1/scholarships/eligible", async () => {
    // Pin: dedicated /eligible endpoint (NOT a query-param
    // overload of base path). Student-facing list filters by
    // current user's role/eligibility on the backend.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createScholarshipsApi();
    await api.getEligible();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/scholarships/eligible");
  });

  // ─── getById ───────────────────────────────────────────────────────

  it("getById GETs /{id} with path param", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createScholarshipsApi();
    await api.getById(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/scholarships/{id}", {
      params: { path: { id: 42 } },
    });
  });

  // ─── getAll ────────────────────────────────────────────────────────

  it("getAll GETs base /api/v1/scholarships path without params", async () => {
    // Pin: admin-facing list — NO /eligible suffix, NO filter
    // params. Backend already gates with require_admin.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createScholarshipsApi();
    await api.getAll();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/scholarships");
  });

  it("getAll passes academic_year+semester query params when provided", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createScholarshipsApi();
    await api.getAll({ academic_year: 113, semester: "first" });
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/scholarships", {
      params: { query: { academic_year: 113, semester: "first" } },
    });
  });

  // ─── getCombined ───────────────────────────────────────────────────

  it("getCombined GETs /combined/list", async () => {
    // Pin: combined scholarships are exposed via /combined/list
    // sub-route. Pin so refactor renaming the route doesn't
    // silently break the admin combined-PhD UI.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createScholarshipsApi();
    await api.getCombined();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/scholarships/combined/list",
      {}
    );
  });

  // ─── createCombinedPhd ─────────────────────────────────────────────

  it("createCombinedPhd POSTs to /combined/phd with body", async () => {
    // Pin: dedicated route distinct from the list route.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createScholarshipsApi();
    await api.createCombinedPhd({
      name: "PhD Combined",
      name_en: "PhD Combined",
      description: "...",
      description_en: "...",
      sub_scholarships: [],
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/scholarships/combined/phd",
      {
        body: {
          name: "PhD Combined",
          name_en: "PhD Combined",
          description: "...",
          description_en: "...",
          sub_scholarships: [],
        },
      }
    );
  });

  it("createCombinedPhd forwards sub_scholarships array verbatim", async () => {
    // Pin: each sub_scholarship has its own fields including
    // sub_type allowlist. Pin to catch any field renaming.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createScholarshipsApi();
    await api.createCombinedPhd({
      name: "x",
      name_en: "x",
      description: "x",
      description_en: "x",
      sub_scholarships: [
        {
          code: "nstc_sub",
          name: "NSTC",
          name_en: "NSTC",
          description: "...",
          description_en: "...",
          sub_type: "nstc",
          amount: 20000,
          min_gpa: 3.5,
          max_ranking_percent: 30,
          required_documents: ["transcript"],
        },
      ],
    });
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.sub_scholarships).toHaveLength(1);
    expect(body.sub_scholarships[0].sub_type).toBe("nstc");
    expect(body.sub_scholarships[0].amount).toBe(20000);
  });

  it("createCombinedPhd accepts both 'nstc' and 'moe' sub_type values", async () => {
    // Pin: the documented allowlist ("nstc" | "moe"). Pin so
    // a refactor adding "education_bureau" requires updating
    // the type + backend Pydantic + this test.
    mockedRaw.POST.mockResolvedValue(_ok({}));
    const api = createScholarshipsApi();
    await api.createCombinedPhd({
      name: "x",
      name_en: "x",
      description: "x",
      description_en: "x",
      sub_scholarships: [
        {
          code: "a",
          name: "a",
          name_en: "a",
          description: "x",
          description_en: "x",
          sub_type: "nstc",
          amount: 100,
        },
        {
          code: "b",
          name: "b",
          name_en: "b",
          description: "x",
          description_en: "x",
          sub_type: "moe",
          amount: 200,
        },
      ],
    });
    const body = mockedRaw.POST.mock.calls[0][1].body;
    const subTypes = body.sub_scholarships.map((s: any) => s.sub_type);
    expect(subTypes).toEqual(["nstc", "moe"]);
  });

  // ─── Verb dispatch invariants ──────────────────────────────────────

  it("read methods use GET, create uses POST", async () => {
    mockedRaw.GET.mockResolvedValue(_ok([]));
    mockedRaw.POST.mockResolvedValue(_ok({}));
    const api = createScholarshipsApi();
    await api.getEligible();
    await api.getAll();
    await api.getCombined();
    await api.getById(1);
    expect(mockedRaw.GET).toHaveBeenCalledTimes(4);
    expect(mockedRaw.POST).not.toHaveBeenCalled();

    await api.createCombinedPhd({
      name: "x",
      name_en: "x",
      description: "x",
      description_en: "x",
      sub_scholarships: [],
    });
    expect(mockedRaw.POST).toHaveBeenCalledTimes(1);
  });

  it("getEligible / getById / getAll all hit /api/v1/scholarships base", async () => {
    // Pin: all 3 read endpoints under the same versioned base.
    mockedRaw.GET.mockResolvedValue(_ok([]));
    const api = createScholarshipsApi();
    await api.getEligible();
    await api.getAll();
    await api.getById(1);
    for (const call of mockedRaw.GET.mock.calls) {
      expect(call[0]).toMatch(/^\/api\/v1\/scholarships/);
    }
  });
});
