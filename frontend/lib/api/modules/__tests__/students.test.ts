/**
 * Tests for `frontend/lib/api/modules/students.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the admin
 * student-management UI: paginated list, stats overview,
 * detail view, real-time SIS data lookup.
 *
 * Wave 6a129 pins URL paths under `/admin/students` (admin
 * scope), query-filter shapes, and the SIS data sub-route
 * which fetches fresh upstream data.
 *
 * 10 cases.
 */

import { createStudentsApi } from "../students";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
    },
  },
}));

const mockedRaw = typedClient.raw as unknown as { GET: jest.Mock };

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createStudentsApi", () => {
  // ─── getAll list with filters ──────────────────────────────────────

  it("getAll GETs /admin/students with all filters", async () => {
    // Pin: 7 optional filters per docstring (page/size/search/
    // dept_code/status/scholarship_type_id/has_application).
    // SNAKE_CASE preserved.
    mockedRaw.GET.mockResolvedValueOnce(
      _ok({ items: [], total: 0, page: 1, size: 20, pages: 0 })
    );
    const api = createStudentsApi();
    await api.getAll({
      page: 2,
      size: 50,
      search: "wang",
      dept_code: "4460",
      status: "在學",
      scholarship_type_id: 3,
      has_application: true,
    });
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/admin/students", {
      params: {
        query: {
          page: 2,
          size: 50,
          search: "wang",
          dept_code: "4460",
          status: "在學",
          scholarship_type_id: 3,
          has_application: true,
        },
      },
    });
  });

  it("getAll passes has_application=false through (not dropped as falsy)", async () => {
    // Pin: `false` filters students who applied for NOTHING —
    // a falsy-check refactor dropping it would silently turn
    // the 未申請 filter into no filter at all.
    mockedRaw.GET.mockResolvedValueOnce(
      _ok({ items: [], total: 0, page: 1, size: 20, pages: 0 })
    );
    const api = createStudentsApi();
    await api.getAll({ has_application: false });
    expect(mockedRaw.GET.mock.calls[0][1].params.query.has_application).toBe(
      false
    );
  });

  it("getAll forwards undefined query when no params", async () => {
    mockedRaw.GET.mockResolvedValueOnce(
      _ok({ items: [], total: 0, page: 1, size: 20, pages: 0 })
    );
    const api = createStudentsApi();
    await api.getAll();
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query).toBeUndefined();
  });

  it("getAll accepts CJK status (在學/畢業) per CLAUDE.md §4", async () => {
    // Pin: CJK status values pass through (EmployeeStatus uses
    // Chinese values per CLAUDE.md §4). Pin so a refactor adding
    // English-only validation doesn't silently break the filter.
    mockedRaw.GET.mockResolvedValueOnce(
      _ok({ items: [], total: 0, page: 1, size: 20, pages: 0 })
    );
    const api = createStudentsApi();
    await api.getAll({ status: "畢業" });
    expect(mockedRaw.GET.mock.calls[0][1].params.query.status).toBe(
      "畢業"
    );
  });

  // ─── getStats ──────────────────────────────────────────────────────

  it("getStats GETs /admin/students/stats", async () => {
    // Pin: dedicated /stats sub-route (NOT query of base path).
    // Admin dashboard reads from this for cards.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createStudentsApi();
    await api.getStats();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/admin/students/stats"
    );
  });

  // ─── getById ───────────────────────────────────────────────────────

  it("getById GETs /admin/students/{user_id}", async () => {
    // Pin: path param uses snake_case key {user_id}. Pin so
    // refactor to camelCase doesn't break the openapi-fetch
    // path template (which matches by key name).
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createStudentsApi();
    await api.getById(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/admin/students/{user_id}",
      { params: { path: { user_id: 42 } } }
    );
  });

  // ─── getSISData ────────────────────────────────────────────────────

  it("getSISData GETs /admin/students/{user_id}/sis-data", async () => {
    // Pin: dedicated /sis-data sub-route. Pin so refactor merging
    // it with getById doesn't silently turn every student-detail
    // fetch into an upstream SIS call (slow + may 404/503).
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createStudentsApi();
    await api.getSISData(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/admin/students/{user_id}/sis-data",
      { params: { path: { user_id: 42 } } }
    );
  });

  // ─── All endpoints under /admin scope ──────────────────────────────

  it("all endpoints share /api/v1/admin/students base (admin scope)", async () => {
    // Pin: all under /admin — backend gates with require_admin.
    // Pin so refactor moving any one outside /admin requires
    // explicit auth migration.
    mockedRaw.GET.mockResolvedValue(
      _ok({ items: [], total: 0, page: 1, size: 20, pages: 0 })
    );
    const api = createStudentsApi();
    await api.getAll();
    await api.getStats();
    await api.getById(1);
    await api.getSISData(1);
    for (const call of mockedRaw.GET.mock.calls) {
      expect(call[0]).toMatch(/^\/api\/v1\/admin\/students/);
    }
  });

  // ─── getStats vs getAll vs getById path distinctness ──────────────

  it("getStats / getById / getSISData all hit distinct sub-paths", async () => {
    // Pin: /stats, /{user_id}, /{user_id}/sis-data are distinct.
    // Pin so refactor merging /stats with /{user_id} would
    // accidentally try to fetch a student with id="stats".
    mockedRaw.GET.mockResolvedValue(_ok({}));
    const api = createStudentsApi();
    await api.getStats();
    await api.getById(1);
    await api.getSISData(1);
    const paths = mockedRaw.GET.mock.calls.map((c) => c[0]);
    expect(new Set(paths).size).toBe(3); // 3 distinct paths
  });

  // ─── No mutation endpoints (read-only module) ──────────────────────

  it("module exposes only read methods (no POST/PUT/PATCH/DELETE)", async () => {
    // Pin: this admin students module is READ-ONLY. Pin so a
    // refactor adding mutations (e.g., suspendStudent) requires
    // explicit review of auth + audit-log policy.
    const api = createStudentsApi();
    expect(api.getAll).toBeDefined();
    expect(api.getStats).toBeDefined();
    expect(api.getById).toBeDefined();
    expect(api.getSISData).toBeDefined();
    // No write methods exposed
    expect((api as any).create).toBeUndefined();
    expect((api as any).update).toBeUndefined();
    expect((api as any).delete).toBeUndefined();
    expect((api as any).suspend).toBeUndefined();
  });
});
