/**
 * Tests for `frontend/lib/api/schemas/user.schema.ts` Zod runtime
 * validators.
 *
 * These schemas guard the boundary between the API and the frontend.
 * If they accept the wrong shape OR reject the right shape, every
 * page that uses the User type breaks:
 *  - Wrong enum values → role-gated routes / nav items render wrong
 *  - Missing required fields silently accepted → undefined access at
 *    runtime
 *
 * Wave 6a103 pins:
 *  - Enum values match the cross-layer wire shape per CLAUDE.md §4
 *    (lowercase for role/user_type; Chinese for status)
 *  - Email field validates email format
 *  - Required fields enforced; optional fields tolerated
 *  - UserListResponse pagination shape
 *
 * 16 cases.
 */

import {
  UserRoleSchema,
  UserTypeSchema,
  UserStatusSchema,
  UserSchema,
  UserListResponseSchema,
} from "../user.schema";

// ─── UserRoleSchema ──────────────────────────────────────────────────

describe("UserRoleSchema", () => {
  it("accepts all 5 documented roles", () => {
    // Pin: matches CLAUDE.md §4 UserRole enum exactly. Adding a
    // role to the enum requires updating this test.
    expect(UserRoleSchema.parse("student")).toBe("student");
    expect(UserRoleSchema.parse("professor")).toBe("professor");
    expect(UserRoleSchema.parse("college")).toBe("college");
    expect(UserRoleSchema.parse("admin")).toBe("admin");
    expect(UserRoleSchema.parse("super_admin")).toBe("super_admin");
  });

  it("rejects uppercase role values", () => {
    // Pin: lowercase wire shape per CLAUDE.md §4. UPPERCASE
    // would mean the frontend is sending enum NAMES instead
    // of values — class of bug we keep catching.
    expect(() => UserRoleSchema.parse("STUDENT")).toThrow();
    expect(() => UserRoleSchema.parse("Admin")).toThrow();
  });

  it("rejects unknown role", () => {
    expect(() => UserRoleSchema.parse("admin_lite")).toThrow();
  });
});

// ─── UserTypeSchema ──────────────────────────────────────────────────

describe("UserTypeSchema", () => {
  it("accepts student and employee", () => {
    // Pin: 2 values per CLAUDE.md §4.
    expect(UserTypeSchema.parse("student")).toBe("student");
    expect(UserTypeSchema.parse("employee")).toBe("employee");
  });

  it("rejects unknown user_type", () => {
    expect(() => UserTypeSchema.parse("intern")).toThrow();
  });
});

// ─── UserStatusSchema ────────────────────────────────────────────────

describe("UserStatusSchema", () => {
  it("accepts all 4 Chinese status values", () => {
    // Pin: EmployeeStatus uses CJK values per CLAUDE.md §4
    // (在職/退休/在學/畢業). Cross-layer wire-shape test —
    // backend Python enum stores these exact strings.
    expect(UserStatusSchema.parse("在學")).toBe("在學");
    expect(UserStatusSchema.parse("畢業")).toBe("畢業");
    expect(UserStatusSchema.parse("在職")).toBe("在職");
    expect(UserStatusSchema.parse("退休")).toBe("退休");
  });

  it("rejects English status values", () => {
    // Pin: English ("active" / "graduated") is NOT accepted —
    // documents the Chinese-only wire shape.
    expect(() => UserStatusSchema.parse("active")).toThrow();
    expect(() => UserStatusSchema.parse("enrolled")).toThrow();
  });
});

// ─── UserSchema ──────────────────────────────────────────────────────

describe("UserSchema", () => {
  function _validUser() {
    return {
      id: "1",
      nycu_id: "310460031",
      email: "test@nycu.edu.tw",
      name: "王小明",
      role: "student" as const,
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-02T00:00:00",
    };
  }

  it("accepts the minimal valid user shape", () => {
    // Pin: required fields = id, nycu_id, email, name, role,
    // created_at, updated_at. Everything else optional.
    const parsed = UserSchema.parse(_validUser());
    expect(parsed.id).toBe("1");
    expect(parsed.role).toBe("student");
  });

  it("rejects when required field missing", () => {
    // Pin: dropping any required field throws. Defensive
    // contract — frontend should not see partial Users.
    const u = _validUser();
    // @ts-expect-error - intentionally omitting required field
    delete u.email;
    expect(() => UserSchema.parse(u)).toThrow();
  });

  it("rejects invalid email format", () => {
    // Pin: email field uses z.string().email() — not just any
    // string. Defends against "lpt" appearing in the email
    // column (real production bug class).
    const u = { ..._validUser(), email: "not-an-email" };
    expect(() => UserSchema.parse(u)).toThrow();
  });

  it("accepts optional fields when present", () => {
    // Pin: optional fields parse cleanly when supplied.
    const u = {
      ..._validUser(),
      user_type: "student",
      status: "在學",
      dept_code: "4460",
      dept_name: "教育博",
      comment: "note",
      last_login_at: "2026-01-03T00:00:00",
      raw_data: { foo: "bar" },
    };
    const parsed = UserSchema.parse(u);
    expect(parsed.user_type).toBe("student");
    expect(parsed.status).toBe("在學");
    expect(parsed.dept_code).toBe("4460");
  });

  it("accepts backward-compat fields (username, full_name, is_active)", () => {
    // Pin: legacy fields still tolerated. Schema documents these
    // as backward-compat — pin so a future cleanup removing them
    // is intentional, not accidental.
    const u = {
      ..._validUser(),
      username: "wangxm",
      full_name: "王小明",
      is_active: true,
    };
    const parsed = UserSchema.parse(u);
    expect(parsed.username).toBe("wangxm");
    expect(parsed.is_active).toBe(true);
  });

  it("rejects user with invalid enum role", () => {
    const u = { ..._validUser(), role: "godking" };
    expect(() => UserSchema.parse(u)).toThrow();
  });
});

// ─── UserListResponseSchema ──────────────────────────────────────────

describe("UserListResponseSchema", () => {
  const _validUser = () => ({
    id: "1",
    nycu_id: "310460031",
    email: "test@nycu.edu.tw",
    name: "王小明",
    role: "student" as const,
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-02T00:00:00",
  });

  it("accepts paginated response with empty items", () => {
    // Pin: empty items array still valid. Pages with no users
    // (e.g., filtered search results) should still parse.
    const resp = UserListResponseSchema.parse({
      items: [],
      total: 0,
      page: 1,
      size: 20,
      pages: 0,
    });
    expect(resp.items).toEqual([]);
    expect(resp.total).toBe(0);
  });

  it("accepts paginated response with multiple users", () => {
    const resp = UserListResponseSchema.parse({
      items: [_validUser(), { ..._validUser(), id: "2" }],
      total: 2,
      page: 1,
      size: 20,
      pages: 1,
    });
    expect(resp.items.length).toBe(2);
  });

  it("requires all 5 pagination fields", () => {
    // Pin: items, total, page, size, pages all required. Pin so
    // a refactor to backend pagination shape doesn't silently
    // drop a field.
    expect(() =>
      UserListResponseSchema.parse({ items: [], total: 0, page: 1 })
    ).toThrow();
  });

  it("rejects non-number total", () => {
    expect(() =>
      UserListResponseSchema.parse({
        items: [],
        total: "0",
        page: 1,
        size: 20,
        pages: 0,
      })
    ).toThrow();
  });

  it("rejects items that don't match UserSchema", () => {
    // Pin: bad item in the list propagates. Can't have a list
    // page where one row passes and another fails silently.
    expect(() =>
      UserListResponseSchema.parse({
        items: [{ ..._validUser(), role: "invalid_role" }],
        total: 1,
        page: 1,
        size: 20,
        pages: 1,
      })
    ).toThrow();
  });
});
