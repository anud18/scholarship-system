/**
 * Tests for `frontend/lib/api/modules/email-management.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the admin
 * email management UI (history, scheduled emails, test mode,
 * audit logs). Heavy module — 19 methods.
 *
 * Wave 6a133 pins the SECURITY-relevant test-mode contract
 * (24h default duration, enable/disable + audit logs) plus
 * the scheduled-email lifecycle (approve/cancel/update/process)
 * and email-history filters. React Email template methods use
 * a fallback base ApiClient and are tested separately if
 * needed.
 *
 * 14 cases focusing on the 12 typedClient-based methods.
 */

import { createEmailManagementApi } from "../email-management";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PATCH: jest.fn(),
    },
  },
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PATCH: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createEmailManagementApi", () => {
  // ─── History & scheduled list ──────────────────────────────────────

  it("getEmailHistory GETs /history with 8 optional filters", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({ items: [], total: 0, skip: 0, limit: 20 }));
    const api = createEmailManagementApi();
    await api.getEmailHistory({
      skip: 0,
      limit: 20,
      email_category: "system",
      status: "sent",
      scholarship_type_id: 1,
      recipient_email: "user@x.com",
      date_from: "2026-01-01",
      date_to: "2026-12-31",
    });
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/email-management/history",
      {
        params: {
          query: {
            skip: 0,
            limit: 20,
            email_category: "system",
            status: "sent",
            scholarship_type_id: 1,
            recipient_email: "user@x.com",
            date_from: "2026-01-01",
            date_to: "2026-12-31",
          },
        },
      }
    );
  });

  it("getScheduledEmails GETs /scheduled with 8 optional filters", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({ items: [], total: 0, skip: 0, limit: 20 }));
    const api = createEmailManagementApi();
    await api.getScheduledEmails({ requires_approval: true });
    expect(mockedRaw.GET.mock.calls[0][0]).toBe(
      "/api/v1/email-management/scheduled"
    );
    expect(
      mockedRaw.GET.mock.calls[0][1].params.query.requires_approval
    ).toBe(true);
  });

  it("getDueScheduledEmails GETs /scheduled/due with optional limit", async () => {
    // Pin: superadmin-only endpoint per docstring. Pin so
    // refactor merging it with /scheduled doesn't accidentally
    // expose due-now emails to non-superadmin.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createEmailManagementApi();
    await api.getDueScheduledEmails(50);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/email-management/scheduled/due",
      { params: { query: { limit: 50 } } }
    );
  });

  // ─── Scheduled email lifecycle ─────────────────────────────────────

  it("approveScheduledEmail PATCHes /{email_id}/approve with approval_notes", async () => {
    // Pin: dedicated /approve sub-route. PATCH = state transition.
    // approval_notes goes via body (NOT query) because admin
    // free-text can be arbitrary length.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createEmailManagementApi();
    await api.approveScheduledEmail(42, "approved by review committee");
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/email-management/scheduled/{email_id}/approve",
      {
        params: { path: { email_id: 42 } },
        body: { approval_notes: "approved by review committee" },
      }
    );
  });

  it("cancelScheduledEmail PATCHes /{email_id}/cancel (no body)", async () => {
    // Pin: cancel has NO body (server toggles status). Pin so
    // refactor adding body doesn't accidentally require admin
    // to specify a reason.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createEmailManagementApi();
    await api.cancelScheduledEmail(42);
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/email-management/scheduled/{email_id}/cancel",
      { params: { path: { email_id: 42 } } }
    );
  });

  it("updateScheduledEmail PATCHes /{email_id} root with subject + body", async () => {
    // Pin: PATCH on /{email_id} (NOT a sub-route). Body has
    // subject AND body fields. Pin so refactor splitting them
    // doesn't break the admin email-edit dialog.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createEmailManagementApi();
    await api.updateScheduledEmail(42, {
      subject: "New subject",
      body: "New body content",
    });
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/email-management/scheduled/{email_id}",
      {
        params: { path: { email_id: 42 } },
        body: { subject: "New subject", body: "New body content" },
      }
    );
  });

  it("processDueEmails POSTs /scheduled/process with optional batch_size", async () => {
    // Pin: superadmin-only batch process. POST (action endpoint),
    // batch_size in QUERY (not body — small integer fits).
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createEmailManagementApi();
    await api.processDueEmails(100);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/email-management/scheduled/process",
      { params: { query: { batch_size: 100 } } }
    );
  });

  // ─── Enumeration endpoints ─────────────────────────────────────────

  it("getEmailCategories GETs /categories", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createEmailManagementApi();
    await api.getEmailCategories();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/email-management/categories"
    );
  });

  it("getEmailStatuses GETs /statuses (returns BOTH email + schedule statuses)", async () => {
    // Pin: single endpoint returns BOTH email_statuses and
    // schedule_statuses arrays. Pin so refactor splitting them
    // doesn't break the dropdown UI that uses both.
    mockedRaw.GET.mockResolvedValueOnce(_ok({ email_statuses: [], schedule_statuses: [] }));
    const api = createEmailManagementApi();
    await api.getEmailStatuses();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/email-management/statuses"
    );
  });

  // ─── Test mode (SECURITY) ──────────────────────────────────────────

  it("getTestModeStatus GETs /test-mode/status", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createEmailManagementApi();
    await api.getTestModeStatus();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/email-management/test-mode/status"
    );
  });

  it("enableTestMode defaults duration_hours=24 + joins email array with commas", async () => {
    // Pin SECURITY: 24h default expiry — test mode auto-disables
    // to prevent stale intercept. Pin so refactor removing the
    // default doesn't leave test-mode active indefinitely.
    // Array of emails joined with comma → backend expects
    // comma-separated string.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createEmailManagementApi();
    await api.enableTestMode({
      redirect_emails: ["test@x.com", "admin@y.com"],
    });
    const query = mockedRaw.POST.mock.calls[0][1].params.query;
    expect(query.redirect_emails).toBe("test@x.com,admin@y.com");
    expect(query.duration_hours).toBe(24);
  });

  it("enableTestMode accepts pre-joined string verbatim", async () => {
    // Pin: if caller already joined the emails, don't double-join.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createEmailManagementApi();
    await api.enableTestMode({
      redirect_emails: "already-joined@x.com",
      duration_hours: 48,
    });
    const query = mockedRaw.POST.mock.calls[0][1].params.query;
    expect(query.redirect_emails).toBe("already-joined@x.com");
    expect(query.duration_hours).toBe(48);
  });

  it("disableTestMode POSTs /test-mode/disable (no body)", async () => {
    // Pin SECURITY: disable doesn't need body — admin click
    // immediately turns off intercept. Pin so refactor adding
    // body (e.g., reason) doesn't add friction to security
    // off-switch.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createEmailManagementApi();
    await api.disableTestMode();
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/email-management/test-mode/disable"
    );
  });

  it("getTestModeAuditLogs GETs /test-mode/audit with optional filters", async () => {
    // Pin: dedicated /audit sub-route for test-mode events
    // (enable/disable/intercept). SECURITY audit trail.
    mockedRaw.GET.mockResolvedValueOnce(_ok({ items: [], total: 0 }));
    const api = createEmailManagementApi();
    await api.getTestModeAuditLogs({ limit: 10, event_type: "enable" });
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/email-management/test-mode/audit",
      { params: { query: { limit: 10, event_type: "enable" } } }
    );
  });

  // ─── Test email send ───────────────────────────────────────────────

  it("sendSimpleTestEmail POSTs /send-simple-test with body", async () => {
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createEmailManagementApi();
    await api.sendSimpleTestEmail({
      recipient_email: "test@x.com",
      subject: "test",
      body: "hello",
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/email-management/send-simple-test",
      { body: { recipient_email: "test@x.com", subject: "test", body: "hello" } }
    );
  });
});
