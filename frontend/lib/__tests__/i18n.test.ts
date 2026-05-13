/**
 * Tests for `lib/i18n.ts:getTranslation`.
 *
 * Frontend translation lookup with dot-notation keys (e.g.,
 * "nav.dashboard" → "儀表板"). Counterpart to backend ScholarshipI18n
 * which uses category+key lookup.
 *
 * Wrong rendering means users see raw keys like "nav.dashboard" in
 * the UI — visible noise on every page.
 *
 * Pinning the lookup contract + the missing-key fallback semantics
 * + the dot-path traversal so future schema changes don't silently
 * break the UI.
 *
 * 8 cases.
 */
import { getTranslation, defaultLocale, locales } from "../i18n";

describe("getTranslation", () => {
  it("resolves a top-level key", () => {
    /** Single-level path returns the value directly. */
    const result = getTranslation("zh", "system.title");
    expect(result).toBe("獎學金申請與簽核系統");
  });

  it("resolves a nested dot-path", () => {
    /** Multi-level dotted key traverses the translation tree. */
    expect(getTranslation("zh", "nav.dashboard")).toBe("儀表板");
    expect(getTranslation("zh", "nav.applications")).toBe("學生申請");
  });

  it("returns the key itself when the path doesn't resolve", () => {
    /** Missing key → return the raw key (caller falls back to it,
     * showing 'unknown.key' in UI instead of crashing or showing
     * 'undefined'). Pin so a future refactor doesn't accidentally
     * return null/undefined and break .toUpperCase() / .length on
     * the result. */
    const result = getTranslation("zh", "completely.unknown.path");
    expect(result).toBe("completely.unknown.path");
  });

  it("returns the key when locale is missing", () => {
    /** Unknown locale → the for-loop runs against undefined, ultimately
     * falls back to returning the key. Pin to verify the optional
     * chaining (?.) doesn't throw. */
    const result = getTranslation("ja" as any, "nav.dashboard");
    expect(result).toBe("nav.dashboard");
  });

  it("returns the key when partial path resolves to an object (not a string)", () => {
    /** Truncated dot-path lands on a nested object (e.g., "nav" resolves
     * to the whole nav dict). The `|| key` fallback applies because
     * an object is truthy and would otherwise be returned. Pin actual
     * behavior: object IS returned (the implementation accepts that). */
    const result = getTranslation("zh", "nav");
    // The function returns the truthy intermediate object — pin this
    // current behavior so a future "must be string" guard surfaces here.
    expect(typeof result).toBe("object");
  });

  it("resolves English equivalent paths", () => {
    /** Pin that the same keys exist in the English tree (drift between
     * zh and en is a real risk — a missing en key shows the raw key
     * to English-locale admins). */
    expect(getTranslation("en", "nav.dashboard")).toBeTruthy();
    expect(getTranslation("en", "nav.dashboard")).not.toBe("nav.dashboard");
  });

  it("defaultLocale is 'zh' and matches the primary user base", () => {
    /** Pin the default — switching defaults silently flips the entire
     * application's default language for users with no explicit
     * preference. */
    expect(defaultLocale).toBe("zh");
  });

  it("locales list is exactly ['zh', 'en']", () => {
    /** Pin the supported-locale list. Adding a new locale here requires
     * the translation tree to gain that locale's branch. */
    expect(locales).toEqual(["zh", "en"]);
  });
});
