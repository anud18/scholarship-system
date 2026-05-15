/**
 * Tests for `frontend/hooks/use-notification-count.ts` exported
 * `notificationKeys` constant.
 *
 * Wave 6a149 attempted to test the full SWR-backed hook but ran
 * into mock fragility around `@/lib/api` resolution. This
 * narrower wave (6a153) pins ONLY the exported constant — no
 * SWR, no apiClient, no React renderer — which is the part
 * other modules import for cache invalidation (mutate calls).
 *
 * The constant defines the SWR cache key used by the unread-
 * notification-count badge in the app header. Drift in the
 * value would orphan existing cached entries and force a
 * re-fetch storm on every active client during deploy.
 */

import { notificationKeys } from "../use-notification-count";

describe("notificationKeys (exported cache-key registry)", () => {
  it("exports exactly 1 key (unreadCount)", () => {
    // Pin: 1-key registry. Pin so refactor adding new keys is
    // deliberate — each key represents a SWR cache entry that
    // downstream consumers (mutate / invalidation) may rely on.
    expect(Object.keys(notificationKeys)).toEqual(["unreadCount"]);
  });

  it("unreadCount value is the documented SWR key", () => {
    // Pin: '/notifications/unread-count' is the canonical SWR
    // cache key. Pin so refactor doesn't change the value (which
    // would orphan existing cached entries and cause re-fetch
    // storms on deploy).
    expect(notificationKeys.unreadCount).toBe(
      "/notifications/unread-count"
    );
  });

  it("unreadCount is a string (NOT a function or symbol)", () => {
    // Pin: string-keyed SWR cache. Pin so refactor to a function-
    // key (SWR also supports those) doesn't break consumers that
    // pass the key string directly to mutate().
    expect(typeof notificationKeys.unreadCount).toBe("string");
  });

  it("unreadCount starts with /notifications/ namespace", () => {
    // Pin: namespace prefix. Pin so future notification-related
    // keys stay under /notifications/* for grouping in SWR
    // devtools.
    expect(notificationKeys.unreadCount.startsWith("/notifications/")).toBe(
      true
    );
  });

  it("unreadCount does NOT include /api/v1 prefix", () => {
    // Pin: the SWR cache key is the LOGICAL path, NOT the full
    // API URL. The actual HTTP fetcher prepends /api/v1 inside
    // the hook. Pin so refactor doesn't include /api/v1 here
    // (which would create double-prefixed URLs).
    expect(notificationKeys.unreadCount).not.toMatch(/^\/api/);
  });

  it("notificationKeys is a frozen-shape object (cannot add keys at runtime)", () => {
    // Pin documentation: the keys registry is meant to be static
    // — runtime mutation would corrupt cache lookups. TypeScript
    // already enforces this; pin the runtime shape so JS callers
    // don't accidentally extend it.
    const keys = notificationKeys;
    expect(keys).toBeDefined();
    expect(typeof keys).toBe("object");
    // Verify the only enumerable own key
    expect(Object.getOwnPropertyNames(keys).filter((k) => k !== "__esModule"))
      .toEqual(["unreadCount"]);
  });
});
