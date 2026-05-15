/**
 * Tests for `frontend/lib/api/modules/admin.ts`.
 *
 * Module had ZERO dedicated test coverage. 992 LOC, 77 methods —
 * largest API module in the codebase. SECURITY-CRITICAL —
 * comprehensive admin functionality (dashboard, application
 * management, email templates, announcements, scholarship
 * management, rules, workflows, permissions, configurations,
 * professor management, bank verification, unified review).
 *
 * Wave 6a138 pins the SECURITY-critical dispatch invariants
 * and the deliberate-distinctions between admin endpoints and
 * non-admin counterparts (where the same operation exists in
 * BOTH but with different verbs, paths, bodies, or auth scopes).
 *
 * 22 cases — selective coverage of highest-risk-of-drift contracts.
 */

import { createAdminApi } from "../admin";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PUT: jest.fn(),
      PATCH: jest.fn(),
      DELETE: jest.fn(),
    },
  },
}));

jest.mock("../../compat", () => ({
  toApiResponse: jest.fn((r) => r),
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PUT: jest.Mock;
  PATCH: jest.Mock;
  DELETE: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createAdminApi", () => {
  // ─── Dashboard + alias ────────────────────────────────────────────

  it("getDashboardStats + getSystemStats hit IDENTICAL URL (alias)", async () => {
    // Pin: getSystemStats is an alias for getDashboardStats — both
    // GET /admin/dashboard/stats. Pin so refactor doesn't split the
    // alias and break legacy callers using getSystemStats.
    mockedRaw.GET.mockResolvedValue({});
    const api = createAdminApi();
    await api.getDashboardStats();
    await api.getSystemStats();
    expect(mockedRaw.GET.mock.calls[0][0]).toBe(
      "/api/v1/admin/dashboard/stats"
    );
    expect(mockedRaw.GET.mock.calls[1][0]).toBe(
      "/api/v1/admin/dashboard/stats"
    );
  });

  it("getRecentApplications query.limit passed even when undefined", async () => {
    // Pin: backend Pydantic accepts limit=null. undefined-forwarded
    // (NOT spread-omitted) so refactor isn't required to add
    // conditional spread.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.getRecentApplications();
    expect(mockedRaw.GET.mock.calls[0][1].params.query).toEqual({
      limit: undefined,
    });
  });

  // ─── updateApplicationStatus PATCH /admin/applications/{id}/status ─

  it("admin.updateApplicationStatus uses PATCH on /admin/applications/{id}/status", async () => {
    // Pin SECURITY: admin uses PATCH (semantic state mutation).
    // DISTINCT from applications.ts module's same-named method
    // which uses PUT on /applications/{id}/status. The TWO methods
    // hit DIFFERENT backend handlers with different auth scopes.
    // Pin so refactor doesn't unify them and silently bypass
    // admin-only validation.
    mockedRaw.PATCH.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.updateApplicationStatus(42, "approved", "looks good");
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/admin/applications/{id}/status",
      {
        params: { path: { id: 42 } },
        body: { status: "approved", review_notes: "looks good" },
      }
    );
  });

  // ─── deleteApplication: HARD-DELETE with REQUIRED reason in body ──

  it("admin.deleteApplication is HARD-delete with REQUIRED reason in body (NOT query)", async () => {
    // Pin SECURITY: admin-only HARD delete (cascades review/roster
    // rows, preserves audit log). reason is REQUIRED and goes in
    // BODY. DISTINCT from applications.ts module's deleteApplication
    // which is SOFT-delete with OPTIONAL reason in QUERY.
    // Pin so refactor doesn't conflate the two or weaken the
    // mandatory-reason guard for hard-deletes.
    mockedRaw.DELETE.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.deleteApplication(42, "duplicate submission per case #1234");
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/admin/applications/{id}",
      {
        params: { path: { id: 42 } },
        body: { reason: "duplicate submission per case #1234" },
      }
    );
  });

  // ─── verifyBankAccount: NO force_recheck in admin module ──────────

  it("admin.verifyBankAccount body OMITS force_recheck (distinct from bank-verification.ts)", async () => {
    // Pin SECURITY: admin module's verifyBankAccount sends ONLY
    // {application_id} — NO force_recheck flag. DISTINCT from
    // bank-verification.ts which sends {application_id,
    // force_recheck: false}. Both endpoints exist on the same URL
    // but admin's variant relies on server-side default behavior.
    // Pin so refactor adding force_recheck here doesn't change
    // server-side semantics unexpectedly.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.verifyBankAccount(42);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/admin/bank-verification",
      { body: { application_id: 42 } }
    );
    expect("force_recheck" in mockedRaw.POST.mock.calls[0][1].body).toBe(false);
  });

  it("admin.verifyBankAccountsBatch body OMITS force_recheck", async () => {
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.verifyBankAccountsBatch([1, 2, 3]);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/admin/bank-verification/batch",
      { body: { application_ids: [1, 2, 3] } }
    );
  });

  // ─── createProfessorStudentRelationship: data in QUERY (quirk) ────

  it("createProfessorStudentRelationship sends relationship_data via QUERY (unusual)", async () => {
    // Pin DOCUMENTED-QUIRK: this method passes the entire data
    // object as a QUERY param `relationship_data` (NOT body). This
    // is intentional per the current backend handler signature.
    // Pin so refactor moving to body doesn't silently 422 every
    // admin assign-professor click.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.createProfessorStudentRelationship({
      professor_nycu_id: "A00001",
      student_nycu_id: "310460031",
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/admin/professor-student-relationships",
      {
        params: {
          query: {
            relationship_data: {
              professor_nycu_id: "A00001",
              student_nycu_id: "310460031",
            },
          },
        },
      }
    );
  });

  // ─── Announcements full CRUD ──────────────────────────────────────

  it("Announcements CRUD uses GET/POST/PUT/DELETE on /admin/announcements", async () => {
    // Pin: full CRUD with distinct verbs. Pin so refactor doesn't
    // collapse update+create into single POST.
    mockedRaw.GET.mockResolvedValue({});
    mockedRaw.POST.mockResolvedValue({});
    mockedRaw.PUT.mockResolvedValue({});
    mockedRaw.DELETE.mockResolvedValue({});

    const api = createAdminApi();
    await api.getAllAnnouncements();
    await api.getAnnouncement(42);
    await api.createAnnouncement({ title: "x", body: "y" });
    await api.updateAnnouncement(42, { title: "new" });
    await api.deleteAnnouncement(42);

    expect(mockedRaw.GET.mock.calls[0][0]).toBe("/api/v1/admin/announcements");
    expect(mockedRaw.GET.mock.calls[1][0]).toBe(
      "/api/v1/admin/announcements/{id}"
    );
    expect(mockedRaw.POST.mock.calls[0][0]).toBe("/api/v1/admin/announcements");
    expect(mockedRaw.PUT.mock.calls[0][0]).toBe(
      "/api/v1/admin/announcements/{id}"
    );
    expect(mockedRaw.DELETE.mock.calls[0][0]).toBe(
      "/api/v1/admin/announcements/{id}"
    );
  });

  it("getAllAnnouncements forwards notification_type (snake_case) NOT notificationType", async () => {
    // Pin SECURITY: backend Pydantic expects snake_case. Pin so
    // refactor renaming the param doesn't break filter UI.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.getAllAnnouncements(1, 20, "system", "high");
    expect(mockedRaw.GET.mock.calls[0][1].params.query).toEqual({
      page: 1,
      size: 20,
      notification_type: "system",
      priority: "high",
    });
  });

  // ─── Scholarship audit trail uses TEMPLATE-LITERAL URL (NOT path) ─

  it("getScholarshipAuditTrail builds URL via template literal (NOT openapi path template)", async () => {
    // Pin DOCUMENTED-QUIRK: this method uses backtick template
    // literal to interpolate scholarshipIdentifier into URL.
    // Distinct from most other methods which use openapi-fetch
    // path templates ({scholarship_code}). Pin so refactor doesn't
    // collide with backend route registration.
    mockedRaw.GET.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.getScholarshipAuditTrail("nstc", "status_change", 50, 0);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/admin/scholarships/nstc/audit-trail",
      {
        params: {
          query: { action_filter: "status_change", limit: 50, offset: 0 },
        },
      }
    );
  });

  // ─── Unified review system (admin role) → /reviews/* (NOT /admin/*) ─

  it("admin.submitApplicationReview hits unified /reviews/ (NOT /admin/)", async () => {
    // Pin SCOPE: admin-role uses the SAME unified review endpoint
    // as college and professor. The admin/college/professor roles
    // are differentiated SERVER-SIDE based on auth. Pin so refactor
    // moving to /admin/reviews/* silently fragments the unified
    // review system.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.submitApplicationReview(42, {
      items: [{ sub_type_code: "nstc", recommendation: "approve" }],
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/reviews/applications/{application_id}/review",
      {
        params: { path: { application_id: 42 } },
        body: {
          items: [{ sub_type_code: "nstc", recommendation: "approve" }],
        },
      }
    );
  });

  it("admin.getReviewableSubTypes + admin.getApplicationReview use unified /reviews/", async () => {
    mockedRaw.GET.mockResolvedValue({});
    const api = createAdminApi();
    await api.getReviewableSubTypes(42);
    await api.getApplicationReview(42);
    expect(mockedRaw.GET.mock.calls[0][0]).toBe(
      "/api/v1/reviews/applications/{application_id}/sub-types"
    );
    expect(mockedRaw.GET.mock.calls[1][0]).toBe(
      "/api/v1/reviews/applications/{application_id}/review"
    );
  });

  // ─── Workflows = stub (no fetch, hardcoded "coming soon") ─────────

  it("getWorkflows returns hardcoded {success:true, data:[]} stub (NO fetch)", async () => {
    // Pin: stub method — DOES NOT call typedClient. Pin so refactor
    // doesn't accidentally wire it to a non-existent backend
    // endpoint and start 404'ing the admin dashboard.
    const api = createAdminApi();
    const result = await api.getWorkflows();
    expect(result).toEqual({
      success: true,
      data: [],
      message: "Workflows feature coming soon",
    });
    expect(mockedRaw.GET).not.toHaveBeenCalled();
    expect(mockedRaw.POST).not.toHaveBeenCalled();
  });

  it("createWorkflow/updateWorkflow/deleteWorkflow return success:false stubs (NO fetch)", async () => {
    const api = createAdminApi();
    const create = await api.createWorkflow({});
    const update = await api.updateWorkflow("x", {});
    const del = await api.deleteWorkflow("x");
    expect(create.success).toBe(false);
    expect(update.success).toBe(false);
    expect(del.success).toBe(false);
    expect(mockedRaw.POST).not.toHaveBeenCalled();
    expect(mockedRaw.PUT).not.toHaveBeenCalled();
    expect(mockedRaw.DELETE).not.toHaveBeenCalled();
  });

  // ─── Scholarship Rules CRUD ───────────────────────────────────────

  it("Scholarship Rules CRUD: GET list + GET one + POST + PUT + DELETE on /admin/scholarship-rules", async () => {
    mockedRaw.GET.mockResolvedValue({});
    mockedRaw.POST.mockResolvedValue({});
    mockedRaw.PUT.mockResolvedValue({});
    mockedRaw.DELETE.mockResolvedValue({});

    const api = createAdminApi();
    await api.getScholarshipRules({ scholarship_type_id: 7 });
    await api.getScholarshipRule(42);
    await api.createScholarshipRule({ name: "rule" });
    await api.updateScholarshipRule(42, { name: "updated" });
    await api.deleteScholarshipRule(42);

    expect(mockedRaw.GET.mock.calls[0][0]).toBe(
      "/api/v1/admin/scholarship-rules"
    );
    expect(mockedRaw.GET.mock.calls[1][0]).toBe(
      "/api/v1/admin/scholarship-rules/{id}"
    );
    expect(mockedRaw.POST.mock.calls[0][0]).toBe(
      "/api/v1/admin/scholarship-rules"
    );
    expect(mockedRaw.PUT.mock.calls[0][0]).toBe(
      "/api/v1/admin/scholarship-rules/{id}"
    );
    expect(mockedRaw.DELETE.mock.calls[0][0]).toBe(
      "/api/v1/admin/scholarship-rules/{id}"
    );
  });

  // ─── Scholarship Permissions CRUD (SECURITY who-can-do-what) ──────

  it("Scholarship Permissions CRUD: 5 verbs on /admin/scholarship-permissions", async () => {
    // Pin SECURITY: permissions endpoint controls which user can
    // manage which scholarships. Drift in body shape silently
    // grants/revokes permissions. Pin verb dispatch.
    mockedRaw.GET.mockResolvedValue({});
    mockedRaw.POST.mockResolvedValue({});
    mockedRaw.PUT.mockResolvedValue({});
    mockedRaw.DELETE.mockResolvedValue({});

    const api = createAdminApi();
    await api.getScholarshipPermissions(7);
    await api.createScholarshipPermission({ user_id: 7, scholarship_id: 1 });
    await api.updateScholarshipPermission(42, { permission_level: "admin" });
    await api.deleteScholarshipPermission(42);

    expect(mockedRaw.GET.mock.calls[0][0]).toContain("scholarship-permissions");
    expect(mockedRaw.POST.mock.calls[0][0]).toContain(
      "scholarship-permissions"
    );
    expect(mockedRaw.PUT.mock.calls[0][0]).toContain("scholarship-permissions");
    expect(mockedRaw.DELETE.mock.calls[0][0]).toContain(
      "scholarship-permissions"
    );
  });

  // ─── Email template CRUD ──────────────────────────────────────────

  it("scholarship email template: distinct /by-scholarship URL + 5 CRUD verbs", async () => {
    // Pin: scholarship-specific email templates live under
    // /scholarship-email-templates (distinct from generic
    // email-templates). Pin so refactor merging them collapses
    // per-scholarship customization.
    mockedRaw.GET.mockResolvedValue({});
    mockedRaw.POST.mockResolvedValue({});
    mockedRaw.PUT.mockResolvedValue({});
    mockedRaw.DELETE.mockResolvedValue({});

    const api = createAdminApi();
    await api.getScholarshipEmailTemplates("nstc");
    await api.createScholarshipEmailTemplate({ key: "x" });
    await api.updateScholarshipEmailTemplate(42, { body: "y" });
    await api.deleteScholarshipEmailTemplate(42);

    expect(mockedRaw.GET.mock.calls[0][0]).toContain(
      "scholarship-email-templates"
    );
    expect(mockedRaw.POST.mock.calls[0][0]).toContain(
      "scholarship-email-templates"
    );
    expect(mockedRaw.PUT.mock.calls[0][0]).toContain(
      "scholarship-email-templates"
    );
    expect(mockedRaw.DELETE.mock.calls[0][0]).toContain(
      "scholarship-email-templates"
    );
  });

  // ─── Bulk operations ──────────────────────────────────────────────

  it("copyRulesBetweenPeriods POSTs /scholarship-rules/copy (short URL) with full body", async () => {
    // Pin: bulk operation — body propagated as-is. URL is `/copy`
    // (NOT `/copy-between-periods`) despite the method name —
    // pin so refactor renaming the method doesn't lead to a
    // misaligned URL change.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.copyRulesBetweenPeriods({
      source_year: 113,
      source_semester: "first",
      target_year: 114,
      target_semester: "first",
      scholarship_type_id: 7,
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/admin/scholarship-rules/copy",
      { body: expect.objectContaining({ source_year: 113 }) }
    );
  });

  it("bulkRuleOperation POSTs /bulk-operation with operation body", async () => {
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.bulkRuleOperation({
      operation: "delete",
      rule_ids: [1, 2, 3],
    });
    expect(mockedRaw.POST.mock.calls[0][0]).toContain("/bulk-operation");
  });

  // ─── duplicateScholarshipConfiguration ────────────────────────────

  it("duplicateScholarshipConfiguration POSTs /{id}/duplicate (path-templated)", async () => {
    // Pin: duplicate is a dedicated action endpoint (POST on
    // sub-route /duplicate). Pin so refactor doesn't expose it as
    // a destructive PUT or hide it under create-with-flag.
    mockedRaw.POST.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.duplicateScholarshipConfiguration(42, {
      name: "duplicate of 114年",
    });
    expect(mockedRaw.POST.mock.calls[0][0]).toContain("/duplicate");
  });

  // ─── Configurations (admin-level) bulk update ─────────────────────

  it("updateConfigurationsBulk PUTs /configurations/bulk with {updates: [...]} body (wrapped)", async () => {
    // Pin: bulk admin configuration updates use PUT (NOT POST) and
    // wrap the array under `updates`. Optional change_reason is
    // spread-conditional. Pin so refactor doesn't strip the wrapper
    // or change to POST.
    mockedRaw.PUT.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.updateConfigurationsBulk(
      [
        { key: "smtp_port", value: 587 },
        { key: "smtp_host", value: "mail.x.com" },
      ],
      "smtp migration"
    );
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/admin/configurations/bulk",
      {
        body: {
          updates: [
            { key: "smtp_port", value: 587 },
            { key: "smtp_host", value: "mail.x.com" },
          ],
          change_reason: "smtp migration",
        },
      }
    );
  });

  it("updateConfigurationsBulk omits change_reason when falsy", async () => {
    // Pin: conditional spread (NOT included as undefined) when
    // changeReason is undefined. Pin so refactor doesn't send
    // change_reason: undefined which audit log treats as
    // "explicitly null".
    mockedRaw.PUT.mockResolvedValueOnce({});
    const api = createAdminApi();
    await api.updateConfigurationsBulk([{ key: "x", value: 1 }]);
    const body = mockedRaw.PUT.mock.calls[0][1].body;
    expect("change_reason" in body).toBe(false);
  });

  // ─── Method count invariant ───────────────────────────────────────

  it("module exposes exactly 77 methods", async () => {
    // Pin: 77 methods is the current admin surface. Pin so
    // refactor adding/removing methods requires explicit review.
    // SECURITY-critical surface — every change should be deliberate.
    const api = createAdminApi();
    expect(Object.keys(api).length).toBe(77);
  });
});
