/**
 * Tests for `frontend/lib/api/modules/email-automation.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the admin
 * email-automation rule UI (CRUD + toggle on/off + trigger
 * event lookup).
 *
 * Wave 6a118 pins URL paths + verb dispatch + query-param
 * construction. Regression silently:
 *  - Routes admin rule edits to wrong endpoint
 *  - Drops filter on rule list page
 *  - Misroutes toggle to PUT (full replace) instead of PATCH
 *    (partial state mutation) — would clobber rule body
 *
 * 11 cases.
 */

import { createEmailAutomationApi } from "../email-automation";
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

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PUT: jest.Mock;
  PATCH: jest.Mock;
  DELETE: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createEmailAutomationApi", () => {
  // ─── getRules ──────────────────────────────────────────────────────

  it("getRules GETs base path with empty query when no params", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createEmailAutomationApi();
    await api.getRules();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/email-automation", {
      params: { query: { is_active: undefined, trigger_event: undefined } },
    });
  });

  it("getRules forwards is_active filter", async () => {
    // Pin: is_active filter passed through. Pin both true and
    // false explicitly (admin needs to filter both ways).
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createEmailAutomationApi();
    await api.getRules({ is_active: true });
    expect(mockedRaw.GET.mock.calls[0][1].params.query.is_active).toBe(true);

    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    await api.getRules({ is_active: false });
    expect(mockedRaw.GET.mock.calls[1][1].params.query.is_active).toBe(false);
  });

  it("getRules forwards trigger_event filter", async () => {
    // Pin: trigger_event SNAKE_CASE — backend Pydantic validates.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createEmailAutomationApi();
    await api.getRules({ trigger_event: "application_submitted" });
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.trigger_event).toBe("application_submitted");
  });

  // ─── createRule ────────────────────────────────────────────────────

  it("createRule POSTs body to base path", async () => {
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createEmailAutomationApi();
    await api.createRule({ name: "x", trigger_event: "y" });
    expect(mockedRaw.POST).toHaveBeenCalledWith("/api/v1/email-automation", {
      body: { name: "x", trigger_event: "y" },
    });
  });

  // ─── updateRule ────────────────────────────────────────────────────

  it("updateRule PUTs to /{id} with body", async () => {
    // Pin: PUT (not PATCH) — full replace. Pin so refactor to
    // PATCH doesn't silently change update semantics (PATCH
    // expects partial; PUT requires complete rule body).
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createEmailAutomationApi();
    await api.updateRule(42, { name: "updated" });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/email-automation/{rule_id}",
      { params: { path: { rule_id: 42 } }, body: { name: "updated" } }
    );
  });

  // ─── deleteRule ────────────────────────────────────────────────────

  it("deleteRule DELETEs /{id}", async () => {
    mockedRaw.DELETE.mockResolvedValueOnce(_ok(undefined));
    const api = createEmailAutomationApi();
    await api.deleteRule(99);
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/email-automation/{rule_id}",
      { params: { path: { rule_id: 99 } } }
    );
  });

  // ─── toggleRule ────────────────────────────────────────────────────

  it("toggleRule PATCHes /{id}/toggle (not PUT)", async () => {
    // Pin: PATCH for state-only toggle. CRITICAL: if this were
    // PUT, an empty body would CLOBBER the rule's name/body/etc.
    // PATCH = partial state update; preserves rule body.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createEmailAutomationApi();
    await api.toggleRule(7);
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/email-automation/{rule_id}/toggle",
      { params: { path: { rule_id: 7 } } }
    );
  });

  it("toggleRule does NOT send a body", async () => {
    // Pin: server toggles based on current state; client sends
    // no body. Pin so refactor adding {is_active: true} body
    // doesn't break the toggle semantics (where current state
    // is authoritative).
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createEmailAutomationApi();
    await api.toggleRule(7);
    const opts = mockedRaw.PATCH.mock.calls[0][1];
    expect(opts).not.toHaveProperty("body");
  });

  // ─── getTriggerEvents ──────────────────────────────────────────────

  it("getTriggerEvents GETs /trigger-events", async () => {
    // Pin: dedicated endpoint for trigger event enumeration.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createEmailAutomationApi();
    await api.getTriggerEvents();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/email-automation/trigger-events"
    );
  });

  // ─── Verb dispatch invariants ──────────────────────────────────────

  it("CRUD verb dispatch: POST/PUT/DELETE used distinctly", async () => {
    // Pin: createRule=POST, updateRule=PUT, deleteRule=DELETE.
    // Pin so a "RESTful cleanup" doesn't accidentally collapse
    // create+update into the same verb.
    mockedRaw.POST.mockResolvedValue(_ok({}));
    mockedRaw.PUT.mockResolvedValue(_ok({}));
    mockedRaw.DELETE.mockResolvedValue(_ok({}));
    const api = createEmailAutomationApi();
    await api.createRule({});
    await api.updateRule(1, {});
    await api.deleteRule(1);
    expect(mockedRaw.POST).toHaveBeenCalledTimes(1);
    expect(mockedRaw.PUT).toHaveBeenCalledTimes(1);
    expect(mockedRaw.DELETE).toHaveBeenCalledTimes(1);
  });

  it("base path is /api/v1/email-automation (not /admin/email-automation)", async () => {
    // Pin: the email automation routes are NOT under /admin/.
    // Pin so a refactor moving them under admin namespace would
    // need explicit auth migration. Backend currently gates with
    // require_admin dep at endpoint level, not URL prefix.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createEmailAutomationApi();
    await api.getRules();
    expect(mockedRaw.GET.mock.calls[0][0]).toBe("/api/v1/email-automation");
  });
});
