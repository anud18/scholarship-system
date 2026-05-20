/**
 * Tests for `frontend/lib/api/modules/notifications.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives all
 * in-app notification flows: list/unread-count/mark-read/
 * mark-all-read/dismiss/detail/admin announcement creation.
 *
 * Wave 6a117 pins URL paths + query-parameter construction +
 * path-templating + admin endpoint routing. Regression here
 * silently:
 *  - Routes to wrong endpoint (404 cascade)
 *  - Drops query filters (returns wrong list)
 *  - Misroutes admin POSTs to non-admin endpoint
 *
 * 13 cases.
 */

import { createNotificationsApi } from "../notifications";
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

beforeEach(() => {
  jest.clearAllMocks();
});

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

describe("createNotificationsApi", () => {
  // ─── getNotifications ───────────────────────────────────────────────

  it("getNotifications GETs base path with no query when no filters", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createNotificationsApi();
    await api.getNotifications();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/notifications", {
      params: {
        query: {
          skip: undefined,
          limit: undefined,
          unread_only: undefined,
          notification_type: undefined,
        },
      },
    });
  });

  it("getNotifications passes all 4 filter params when provided", async () => {
    // Pin: skip/limit/unread_only/notification_type forwarded
    // verbatim. Pin so renaming silently breaks filter UI.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createNotificationsApi();
    await api.getNotifications(10, 50, true, "app_status_change");
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/notifications", {
      params: {
        query: {
          skip: 10,
          limit: 50,
          unread_only: true,
          notification_type: "app_status_change",
        },
      },
    });
  });

  it("getNotifications snake_case query keys (not camelCase)", async () => {
    // Pin: backend expects unread_only / notification_type (snake).
    // Pin so a refactor to camelCase silently breaks the filter.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createNotificationsApi();
    await api.getNotifications(undefined, undefined, true, undefined);
    const call = mockedRaw.GET.mock.calls[0];
    const query = call[1].params.query;
    expect(query).toHaveProperty("unread_only");
    expect(query).toHaveProperty("notification_type");
    expect(query).not.toHaveProperty("unreadOnly");
    expect(query).not.toHaveProperty("notificationType");
  });

  // ─── getUnreadCount ─────────────────────────────────────────────────

  it("getUnreadCount GETs /unread-count", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok(5));
    const api = createNotificationsApi();
    await api.getUnreadCount();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/notifications/unread-count"
    );
  });

  // ─── markAsRead ─────────────────────────────────────────────────────

  it("markAsRead PATCHes /{id}/read with path param", async () => {
    // Pin: id templated into path. Verb is PATCH (not POST/PUT).
    // Pin so refactor to POST breaks the backend handler.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({}));
    const api = createNotificationsApi();
    await api.markAsRead(42);
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/notifications/{notification_id}/read",
      { params: { path: { notification_id: 42 } } }
    );
  });

  // ─── markAllAsRead ──────────────────────────────────────────────────

  it("markAllAsRead PATCHes /mark-all-read without body", async () => {
    // Pin: PATCH verb + dedicated endpoint (NOT a query-param
    // overload of /read). Mass operation deserves explicit route.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({ updated_count: 5 }));
    const api = createNotificationsApi();
    await api.markAllAsRead();
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/notifications/mark-all-read"
    );
  });

  // ─── dismiss ────────────────────────────────────────────────────────

  it("dismiss PATCHes /{id}/dismiss with path param", async () => {
    // Pin: dismiss is SEPARATE from read (dismissed = hidden;
    // read = acknowledged). Pin so admins don't accidentally
    // merge the two endpoints.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({ notification_id: 7 }));
    const api = createNotificationsApi();
    await api.dismiss(7);
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/notifications/{notification_id}/dismiss",
      { params: { path: { notification_id: 7 } } }
    );
  });

  // ─── getNotificationDetail ──────────────────────────────────────────

  it("getNotificationDetail GETs /{id}", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({ id: 1, title: "x" }));
    const api = createNotificationsApi();
    await api.getNotificationDetail(99);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/notifications/{notification_id}",
      { params: { path: { notification_id: 99 } } }
    );
  });

  // ─── createSystemAnnouncement (admin) ───────────────────────────────

  it("createSystemAnnouncement POSTs admin endpoint", async () => {
    // Pin: ADMIN endpoint path "/admin/create-system-announcement".
    // Pin so refactor to non-admin path doesn't bypass auth check.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createNotificationsApi();
    await api.createSystemAnnouncement({
      title: "Maintenance",
      message: "...",
      notification_type: "system",
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/notifications/admin/create-system-announcement",
      { body: { title: "Maintenance", message: "...", notification_type: "system" } }
    );
  });

  it("createSystemAnnouncement forwards target_roles when provided", async () => {
    // Pin: target_roles array forwarded verbatim. Used to scope
    // announcements to specific user roles.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createNotificationsApi();
    await api.createSystemAnnouncement({
      title: "x",
      message: "y",
      target_roles: ["student", "professor"],
    });
    const call = mockedRaw.POST.mock.calls[0];
    expect(call[1].body.target_roles).toEqual(["student", "professor"]);
  });

  // ─── createTestNotifications (admin) ────────────────────────────────

  it("createTestNotifications POSTs admin test endpoint", async () => {
    // Pin: admin-only test notification factory. Pin path so
    // refactor doesn't accidentally open this to non-admins.
    mockedRaw.POST.mockResolvedValueOnce(_ok({ created_count: 3 }));
    const api = createNotificationsApi();
    await api.createTestNotifications();
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/notifications/admin/create-test-notifications"
    );
  });

  // ─── Method dispatch invariants ────────────────────────────────────

  it("read-state mutations use PATCH (not POST)", async () => {
    // Pin: markAsRead / markAllAsRead / dismiss → PATCH. Documents
    // RESTful intent (PATCH = partial update of resource state).
    mockedRaw.PATCH.mockResolvedValue(_ok({}));
    const api = createNotificationsApi();
    await api.markAsRead(1);
    await api.markAllAsRead();
    await api.dismiss(2);
    expect(mockedRaw.PATCH).toHaveBeenCalledTimes(3);
    expect(mockedRaw.POST).not.toHaveBeenCalled();
  });

  it("admin-only methods use POST (not PATCH)", async () => {
    // Pin: createSystemAnnouncement / createTestNotifications →
    // POST (new resource creation, not state mutation).
    mockedRaw.POST.mockResolvedValue(_ok({}));
    const api = createNotificationsApi();
    await api.createSystemAnnouncement({ title: "x", message: "y" });
    await api.createTestNotifications();
    expect(mockedRaw.POST).toHaveBeenCalledTimes(2);
  });
});
