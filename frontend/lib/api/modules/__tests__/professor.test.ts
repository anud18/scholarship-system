/**
 * Tests for `frontend/lib/api/modules/professor.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the professor
 * review UI: see assigned applications, submit/update reviews
 * with per-sub-type recommendations.
 *
 * Wave 6a128 pins URL paths + the special getApplications
 * pagination-unwrap behavior + recommendation enum allowlist
 * ('approve' | 'reject', NOT boolean) + error fallback shape.
 *
 * 14 cases.
 */

import { createProfessorApi } from "../professor";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PUT: jest.fn(),
    },
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

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createProfessorApi", () => {
  // ─── getApplications (pagination unwrap) ───────────────────────────

  it("getApplications unwraps paginated response into flat array", async () => {
    // Pin: backend returns PaginatedResponse<Application>, but
    // the professor UI expects a flat array. This module unwraps
    // .data.items → data. Pin so refactor preserving the
    // paginated shape doesn't silently break the UI.
    mockedRaw.GET.mockResolvedValueOnce(
      _ok({
        items: [{ id: 1 }, { id: 2 }],
        total: 2,
        page: 1,
        size: 50,
        pages: 1,
      })
    );
    const api = createProfessorApi();
    const result = await api.getApplications();
    expect(result.success).toBe(true);
    expect(result.data).toEqual([{ id: 1 }, { id: 2 }]);
  });

  it("getApplications forwards status_filter query param", async () => {
    mockedRaw.GET.mockResolvedValueOnce(
      _ok({ items: [], total: 0, page: 1, size: 50, pages: 0 })
    );
    const api = createProfessorApi();
    await api.getApplications("pending");
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/professor/applications",
      { params: { query: { status_filter: "pending" } } }
    );
  });

  it("getApplications returns empty array + error message when shape unexpected", async () => {
    // Pin: fallback path when data.items is not an array (e.g.,
    // backend returns wrong shape). Pin so the UI gets a safe
    // empty list rather than crashing.
    mockedRaw.GET.mockResolvedValueOnce(_ok({ unexpected: "shape" }));
    const api = createProfessorApi();
    const result = await api.getApplications();
    expect(result.success).toBe(false);
    expect(result.data).toEqual([]);
    expect(result.message).toContain("unexpected response format");
  });

  it("getApplications returns empty array + error message on exception", async () => {
    // Pin: catch path — network error or thrown exception
    // becomes a safe ApiResponse with success=false + empty array.
    mockedRaw.GET.mockRejectedValueOnce(new Error("network fail"));
    const api = createProfessorApi();
    const result = await api.getApplications();
    expect(result.success).toBe(false);
    expect(result.data).toEqual([]);
    expect(result.message).toBe("network fail");
  });

  // ─── getReview ─────────────────────────────────────────────────────

  it("getReview GETs /applications/{application_id}/review", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createProfessorApi();
    await api.getReview(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/professor/applications/{application_id}/review",
      { params: { path: { application_id: 42 } } }
    );
  });

  // ─── submitReview (NEW recommendation enum format) ─────────────────

  it("submitReview POSTs review with recommendation enum (approve|reject)", async () => {
    // Pin NEW FORMAT: recommendation is enum 'approve' | 'reject'
    // (NOT boolean is_recommended). Pin so refactor reviving the
    // old boolean breaks backend Pydantic validator that expects
    // the enum.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createProfessorApi();
    await api.submitReview(7, {
      items: [
        { sub_type_code: "nstc", recommendation: "approve" },
        { sub_type_code: "moe", recommendation: "reject", comments: "no" },
      ],
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/professor/applications/{application_id}/review",
      {
        params: { path: { application_id: 7 } },
        body: {
          items: [
            { sub_type_code: "nstc", recommendation: "approve" },
            { sub_type_code: "moe", recommendation: "reject", comments: "no" },
          ],
        },
      }
    );
  });

  it("submitReview body items support optional comments", async () => {
    // Pin: comments optional per item — admin/professor can
    // omit when no rationale needed.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createProfessorApi();
    await api.submitReview(7, {
      items: [{ sub_type_code: "nstc", recommendation: "approve" }],
    });
    const body = mockedRaw.POST.mock.calls[0][1].body;
    expect(body.items[0].comments).toBeUndefined();
  });

  // ─── updateReview ──────────────────────────────────────────────────

  it("updateReview PUTs /review/{review_id} sub-route", async () => {
    // Pin: update goes to /review/{review_id} (NOT /review root).
    // Pin so refactor merging submit+update into one endpoint
    // doesn't silently lose the review-version distinction.
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createProfessorApi();
    await api.updateReview(7, 99, {
      items: [{ sub_type_code: "nstc", recommendation: "reject" }],
    });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/professor/applications/{application_id}/review/{review_id}",
      {
        params: { path: { application_id: 7, review_id: 99 } },
        body: {
          items: [{ sub_type_code: "nstc", recommendation: "reject" }],
        },
      }
    );
  });

  it("updateReview also uses recommendation enum (not is_recommended)", async () => {
    // Pin: same enum format as submit. Pin so refactor doesn't
    // accidentally diverge submit vs update bodies.
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createProfessorApi();
    await api.updateReview(7, 99, {
      items: [{ sub_type_code: "nstc", recommendation: "approve" }],
    });
    const body = mockedRaw.PUT.mock.calls[0][1].body;
    expect(body.items[0]).toHaveProperty("recommendation");
    expect(body.items[0]).not.toHaveProperty("is_recommended");
  });

  // ─── getSubTypes ───────────────────────────────────────────────────

  it("getSubTypes GETs /applications/{id}/sub-types", async () => {
    // Pin: sub-types are per-application (filtered by what the
    // student applied for). Pin so refactor to a global
    // /sub-types endpoint doesn't bypass per-app filtering.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createProfessorApi();
    await api.getSubTypes(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/professor/applications/{application_id}/sub-types",
      { params: { path: { application_id: 42 } } }
    );
  });

  // ─── getStats ──────────────────────────────────────────────────────

  it("getStats GETs /professor/stats (no path/query)", async () => {
    // Pin: dashboard stats for the current professor. Backend
    // scopes by request user. Pin so refactor adding a path
    // param doesn't silently expose other professors' stats.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createProfessorApi();
    await api.getStats();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/professor/stats");
  });

  // ─── Verb dispatch invariants ──────────────────────────────────────

  it("review submit uses POST; review update uses PUT (not PATCH)", async () => {
    // Pin: full-replace semantics on both. PATCH semantics
    // (partial update) would change behavior — pin so refactor
    // doesn't silently allow partial review updates that leak
    // stale item state.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createProfessorApi();
    await api.submitReview(1, { items: [] });
    await api.updateReview(1, 1, { items: [] });
    expect(mockedRaw.POST).toHaveBeenCalledTimes(1);
    expect(mockedRaw.PUT).toHaveBeenCalledTimes(1);
  });

  it("all endpoints share /api/v1/professor base", async () => {
    mockedRaw.GET.mockResolvedValue(
      _ok({ items: [], total: 0, page: 1, size: 50, pages: 0 })
    );
    mockedRaw.POST.mockResolvedValue(_ok({}));
    mockedRaw.PUT.mockResolvedValue(_ok({}));
    const api = createProfessorApi();
    await api.getApplications();
    await api.getReview(1);
    await api.submitReview(1, { items: [] });
    await api.updateReview(1, 1, { items: [] });
    await api.getSubTypes(1);
    await api.getStats();
    const allPaths = [
      ...mockedRaw.GET.mock.calls.map((c) => c[0]),
      ...mockedRaw.POST.mock.calls.map((c) => c[0]),
      ...mockedRaw.PUT.mock.calls.map((c) => c[0]),
    ];
    for (const path of allPaths) {
      expect(path).toMatch(/^\/api\/v1\/professor/);
    }
  });

  it("getApplications graceful fallback never propagates throw", async () => {
    // Pin: try/catch ensures the UI gets ApiResponse always,
    // not an unhandled rejection. Critical for the professor
    // dashboard.
    mockedRaw.GET.mockRejectedValueOnce("some-non-error-throw");
    const api = createProfessorApi();
    const result = await api.getApplications();
    expect(result.success).toBe(false);
    expect(result.data).toEqual([]);
  });
});
