/**
 * Tests for `frontend/lib/api/modules/users.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives both:
 *  - Self-service (getProfile / updateProfile / getStudentInfo /
 *    updateStudentInfo) → student-facing
 *  - Admin CRUD (getAll / getById / create / update / delete /
 *    resetPassword / getStats)
 *
 * Wave 6a126 pins URL paths + verb dispatch + the asymmetric
 * routes (self vs /{id} vs /me).
 *
 * 13 cases.
 */

import { createUsersApi } from "../users";
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

describe("createUsersApi", () => {
  // ─── Self-service ──────────────────────────────────────────────────

  it("getProfile GETs /users/me", async () => {
    // Pin: /me is the documented self-service endpoint. Pin so
    // refactor doesn't accidentally route to /{id} (which would
    // 403 the current user without admin role).
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.getProfile();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/users/me");
  });

  it("updateProfile PUTs /users/me with body", async () => {
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.updateProfile({ name: "Updated" } as any);
    expect(mockedRaw.PUT).toHaveBeenCalledWith("/api/v1/users/me", {
      body: { name: "Updated" },
    });
  });

  it("getStudentInfo GETs /users/student-info", async () => {
    // Pin: dedicated student-info sub-route (NOT a query of /me).
    // Returns SIS-fetched data, not the User row.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.getStudentInfo();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/users/student-info"
    );
  });

  it("updateStudentInfo PUTs /users/student-info", async () => {
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.updateStudentInfo({ gpa: 3.8 });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/users/student-info",
      { body: { gpa: 3.8 } }
    );
  });

  // ─── Admin CRUD ────────────────────────────────────────────────────

  it("getAll GETs /users with optional pagination/filter params", async () => {
    // Pin: 4 optional filters (page/size/role/search). Pin so
    // omitting params doesn't send empty object.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.getAll({ page: 1, size: 50, role: "student", search: "wang" });
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/users", {
      params: { query: { page: 1, size: 50, role: "student", search: "wang" } },
    });
  });

  it("getAll uses undefined query when no params", async () => {
    // Pin: omitted params → query is the user-supplied undefined
    // (not empty object). Pin so refactor doesn't accidentally
    // send {} which some backend validators reject.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.getAll();
    expect(mockedRaw.GET.mock.calls[0][1].params.query).toBeUndefined();
  });

  it("getById GETs /users/{id}", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.getById(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/users/{id}", {
      params: { path: { id: 42 } },
    });
  });

  it("create POSTs body to /users base path", async () => {
    // Pin: NOT /{id} — POST to collection root. Pin role/user_type/
    // status enum-allowlist values forwarded verbatim.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.create({
      nycu_id: "310460031",
      email: "wang@nycu.edu.tw",
      name: "王小明",
      role: "student",
      user_type: "student",
      status: "在學",
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith("/api/v1/users", {
      body: {
        nycu_id: "310460031",
        email: "wang@nycu.edu.tw",
        name: "王小明",
        role: "student",
        user_type: "student",
        status: "在學",
      },
    });
  });

  it("update PUTs /users/{id} with body", async () => {
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.update(7, { status: "畢業" });
    expect(mockedRaw.PUT).toHaveBeenCalledWith("/api/v1/users/{id}", {
      params: { path: { id: 7 } },
      body: { status: "畢業" },
    });
  });

  it("delete DELETEs /users/{id}", async () => {
    // Pin: hard delete (per docstring). Pin so refactor to soft-
    // delete via PATCH doesn't silently change semantics —
    // changing from hard to soft delete is a data-retention
    // policy decision that needs explicit review.
    mockedRaw.DELETE.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.delete(7);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith("/api/v1/users/{id}", {
      params: { path: { id: 7 } },
    });
  });

  it("resetPassword POSTs /users/{id}/reset-password", async () => {
    // Pin: POST (not PUT/PATCH) — it's an action endpoint, not
    // a resource update. The endpoint is documented as "not
    // supported in SSO model" — pin so future SSO migration
    // doesn't accidentally route it to a real password reset.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.resetPassword(7);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/users/{id}/reset-password",
      { params: { path: { id: 7 } } }
    );
  });

  it("getStats GETs /users/stats/overview", async () => {
    // Pin: nested /stats/overview path (NOT a query-param of base).
    // Admin dashboard reads from this dedicated stats endpoint.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createUsersApi();
    await api.getStats();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/users/stats/overview"
    );
  });

  // ─── Verb dispatch invariants ──────────────────────────────────────

  it("self-service uses /me; admin uses /{id} — paths are distinct", async () => {
    // Pin: /me and /{id} are DIFFERENT endpoints with DIFFERENT
    // auth scopes. Pin so refactor merging them (e.g., /{id} with
    // server-side "me" alias) needs explicit migration.
    mockedRaw.PUT.mockResolvedValue(_ok({}));
    const api = createUsersApi();
    await api.updateProfile({} as any);
    await api.update(1, {});
    expect(mockedRaw.PUT.mock.calls[0][0]).toBe("/api/v1/users/me");
    expect(mockedRaw.PUT.mock.calls[1][0]).toBe("/api/v1/users/{id}");
  });
});
