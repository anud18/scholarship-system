/**
 * Tests for `frontend/lib/api/modules/professor-student.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the admin
 * professor-student relationship CRUD UI.
 *
 * Wave 6a121 pins:
 *  - URL paths + path templating
 *  - Distinct CRUD verb dispatch (GET / POST / PUT / DELETE)
 *  - List endpoint query-string construction (6 filters)
 *  - Quirk: CREATE uses query-string (not body) — pin so a
 *    refactor to body doesn't break backend handler that
 *    reads from query
 *
 * 10 cases.
 */

import { createProfessorStudentApi } from "../professor-student";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PUT: jest.fn(),
      DELETE: jest.fn(),
    },
  },
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PUT: jest.Mock;
  DELETE: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createProfessorStudentApi", () => {
  // ─── getProfessorStudentRelationships ──────────────────────────────

  it("getProfessorStudentRelationships GETs base path with empty query", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createProfessorStudentApi();
    await api.getProfessorStudentRelationships();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/professor-student", {
      params: {
        query: {
          professor_id: undefined,
          student_id: undefined,
          relationship_type: undefined,
          status: undefined,
          page: undefined,
          size: undefined,
        },
      },
    });
  });

  it("getProfessorStudentRelationships forwards all 6 filter params", async () => {
    // Pin: 6 filter knobs — pin so renaming silently breaks
    // admin search UI. SNAKE_CASE keys pinned (backend Pydantic).
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createProfessorStudentApi();
    await api.getProfessorStudentRelationships({
      professor_id: 1,
      student_id: 2,
      relationship_type: "advisor",
      status: "active",
      page: 1,
      size: 50,
    });
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.professor_id).toBe(1);
    expect(query.student_id).toBe(2);
    expect(query.relationship_type).toBe("advisor");
    expect(query.status).toBe("active");
    expect(query.page).toBe(1);
    expect(query.size).toBe(50);
  });

  // ─── createProfessorStudentRelationship — quirk: uses query, not body ─

  it("createProfessorStudentRelationship POSTs base path", async () => {
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createProfessorStudentApi();
    await api.createProfessorStudentRelationship({
      professor_id: 1,
      student_id: 2,
      relationship_type: "advisor",
    });
    expect(mockedRaw.POST.mock.calls[0][0]).toBe("/api/v1/professor-student");
  });

  it("createProfessorStudentRelationship passes data via QUERY (not body)", async () => {
    // Pin DOCUMENTED QUIRK: this endpoint reads from query
    // string, not request body. Pin so a "RESTful cleanup"
    // refactor to body breaks backend (until backend is updated
    // to match). This is the kind of cross-layer contract that
    // silent refactors easily break.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createProfessorStudentApi();
    await api.createProfessorStudentRelationship({
      professor_id: 7,
      student_id: 8,
      relationship_type: "co_advisor",
    });
    const opts = mockedRaw.POST.mock.calls[0][1];
    expect(opts.params.query.professor_id).toBe(7);
    expect(opts.params.query.relationship_type).toBe("co_advisor");
    expect(opts).not.toHaveProperty("body");
  });

  // ─── updateProfessorStudentRelationship ────────────────────────────

  it("updateProfessorStudentRelationship PUTs /{id} with body", async () => {
    // Pin: update DOES use body (unlike create's quirk).
    // Different contract — pin both to document the asymmetry.
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createProfessorStudentApi();
    await api.updateProfessorStudentRelationship(42, {
      status: "inactive",
      end_date: "2026-01-01",
    });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/professor-student/{id}",
      {
        params: { path: { id: 42 } },
        body: { status: "inactive", end_date: "2026-01-01" },
      }
    );
  });

  it("updateProfessorStudentRelationship uses PUT (not PATCH)", async () => {
    // Pin: PUT semantics — admin re-sends the relationship.
    // Pin so refactor to PATCH doesn't silently change update
    // contract (PATCH expects partial; PUT replaces).
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createProfessorStudentApi();
    await api.updateProfessorStudentRelationship(1, {});
    expect(mockedRaw.PUT).toHaveBeenCalled();
  });

  // ─── deleteProfessorStudentRelationship ───────────────────────────

  it("deleteProfessorStudentRelationship DELETEs /{id}", async () => {
    mockedRaw.DELETE.mockResolvedValueOnce(_ok(undefined));
    const api = createProfessorStudentApi();
    await api.deleteProfessorStudentRelationship(99);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/professor-student/{id}",
      { params: { path: { id: 99 } } }
    );
  });

  // ─── Verb dispatch invariants ─────────────────────────────────────

  it("CRUD verb dispatch: GET/POST/PUT/DELETE used distinctly", async () => {
    mockedRaw.GET.mockResolvedValue(_ok([]));
    mockedRaw.POST.mockResolvedValue(_ok({}));
    mockedRaw.PUT.mockResolvedValue(_ok({}));
    mockedRaw.DELETE.mockResolvedValue(_ok(undefined));
    const api = createProfessorStudentApi();
    await api.getProfessorStudentRelationships();
    await api.createProfessorStudentRelationship({
      professor_id: 1,
      student_id: 2,
      relationship_type: "x",
    });
    await api.updateProfessorStudentRelationship(1, {});
    await api.deleteProfessorStudentRelationship(1);
    expect(mockedRaw.GET).toHaveBeenCalledTimes(1);
    expect(mockedRaw.POST).toHaveBeenCalledTimes(1);
    expect(mockedRaw.PUT).toHaveBeenCalledTimes(1);
    expect(mockedRaw.DELETE).toHaveBeenCalledTimes(1);
  });

  it("all paths share /api/v1/professor-student base", async () => {
    mockedRaw.GET.mockResolvedValue(_ok([]));
    mockedRaw.POST.mockResolvedValue(_ok({}));
    mockedRaw.PUT.mockResolvedValue(_ok({}));
    mockedRaw.DELETE.mockResolvedValue(_ok(undefined));
    const api = createProfessorStudentApi();
    await api.getProfessorStudentRelationships();
    await api.createProfessorStudentRelationship({
      professor_id: 1,
      student_id: 2,
      relationship_type: "x",
    });
    await api.updateProfessorStudentRelationship(1, {});
    await api.deleteProfessorStudentRelationship(1);
    const allPaths = [
      mockedRaw.GET.mock.calls[0][0],
      mockedRaw.POST.mock.calls[0][0],
      mockedRaw.PUT.mock.calls[0][0],
      mockedRaw.DELETE.mock.calls[0][0],
    ];
    for (const path of allPaths) {
      expect(path).toMatch(/^\/api\/v1\/professor-student/);
    }
  });

  it("update + delete share the same /{id} path", async () => {
    // Pin: both ID-scoped operations use the same path
    // template. Pin so refactor diverging the URL silently
    // breaks DELETE handler routing.
    mockedRaw.PUT.mockResolvedValue(_ok({}));
    mockedRaw.DELETE.mockResolvedValue(_ok(undefined));
    const api = createProfessorStudentApi();
    await api.updateProfessorStudentRelationship(1, {});
    await api.deleteProfessorStudentRelationship(1);
    expect(mockedRaw.PUT.mock.calls[0][0]).toBe(mockedRaw.DELETE.mock.calls[0][0]);
  });
});
