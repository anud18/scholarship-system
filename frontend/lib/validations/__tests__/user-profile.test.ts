/**
 * Tests for `lib/validations/user-profile.ts` — frontend mirror of the
 * backend `AdvisorInfoBase` / `BankInfoUpdate` Pydantic validators
 * (covered separately in backend `test_cron_email_schema_validators.py`).
 *
 * Frontend-side validation provides the fast inline-feedback UX. Backend
 * is the authoritative gate; this frontend mirror MUST stay in sync —
 * a drift would cause UX confusion (form passes locally then fails on
 * submit) or worse, silently let invalid data slip through if the
 * backend gate is bypassed.
 *
 * Bugs cause:
 * - `validateAdvisorEmail`: invalid email accepted client-side → fails
 *   loudly on submit (UX bug)
 * - `validateBankInfo`: wrong-digit-count postal account accepted →
 *   bank transfer rejected on payment day (silent until too late)
 * - `sanitizeAdvisorEmail`: empty string sent to API instead of
 *   undefined → API treats `''` as 'set to empty' rather than 'unset',
 *   stale empty record persists
 * - `sanitizeBankInfo`: spaces/hyphens not stripped → '12-34 5678' in DB
 *   instead of canonical '12345678' → downstream lookups miss
 *
 * 8 helpers (22 cases). Pure functions, no DOM / no fetch.
 */

import {
  sanitizeAdvisorEmail,
  sanitizeAdvisorInfo,
  sanitizeBankInfo,
  validateAdvisorEmail,
  validateAdvisorInfo,
  validateBankInfo,
} from "../user-profile";

// ─── validateAdvisorEmail ────────────────────────────────────────────

describe("validateAdvisorEmail", () => {
  it("treats empty/null/undefined as valid (optional field)", () => {
    /* Pin: optional field — empty string is NOT an error here. The
     * sanitizer converts it to `undefined` before API submission. */
    expect(validateAdvisorEmail("").isValid).toBe(true);
    expect(validateAdvisorEmail(null).isValid).toBe(true);
    expect(validateAdvisorEmail(undefined).isValid).toBe(true);
    expect(validateAdvisorEmail("   ").isValid).toBe(true); // whitespace
  });

  it("accepts valid email formats", () => {
    expect(validateAdvisorEmail("prof@nycu.edu.tw").isValid).toBe(true);
    expect(validateAdvisorEmail("user+tag@example.co").isValid).toBe(true);
    expect(validateAdvisorEmail("a.b.c@d.e").isValid).toBe(true);
  });

  it("rejects malformed emails with localized error message", () => {
    const result = validateAdvisorEmail("not-an-email");
    expect(result.isValid).toBe(false);
    /* Pin: error message includes the Chinese hint AND an example
     * — UI relies on this string format. */
    expect(result.errors[0]).toContain("Email");
    expect(result.errors[0]).toContain("professor@nycu.edu.tw");
  });

  it("rejects emails with spaces", () => {
    expect(validateAdvisorEmail("two words@example.com").isValid).toBe(false);
  });

  it("rejects emails missing TLD or @ symbol", () => {
    expect(validateAdvisorEmail("no-at-sign.com").isValid).toBe(false);
    expect(validateAdvisorEmail("user@no-tld").isValid).toBe(false);
  });
});

// ─── validateAdvisorInfo (composite) ─────────────────────────────────

describe("validateAdvisorInfo", () => {
  it("requires all 3 advisor fields", () => {
    /* Pin: REQUIRED for advisor info submission (unlike standalone
     * email validation which treats empty as valid optional). The
     * full-info flow is the 'I am submitting an application that
     * needs a professor recommendation' path. */
    const result = validateAdvisorInfo({});
    expect(result.isValid).toBe(false);
    expect(result.errors).toHaveLength(3); // name + email + nycu_id all missing
  });

  it("rejects when advisor_name exceeds 100 chars", () => {
    /* Pin: max_length=100 matches the backend `String(100)` DB column. */
    const result = validateAdvisorInfo({
      advisor_name: "x".repeat(101),
      advisor_email: "p@nycu.edu.tw",
      advisor_nycu_id: "A0001",
    });
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("100"))).toBe(true);
  });

  it("rejects when nycu_id exceeds 20 chars", () => {
    /* Pin: max_length=20 matches backend. */
    const result = validateAdvisorInfo({
      advisor_name: "Prof Wang",
      advisor_email: "p@nycu.edu.tw",
      advisor_nycu_id: "x".repeat(21),
    });
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("20"))).toBe(true);
  });

  it("propagates email format errors from validateAdvisorEmail", () => {
    /* Pin: composite validator delegates email format to
     * validateAdvisorEmail — drift here would mean a refactor only
     * touching one side. */
    const result = validateAdvisorInfo({
      advisor_name: "Prof Wang",
      advisor_email: "garbage",
      advisor_nycu_id: "A0001",
    });
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("Email"))).toBe(true);
  });

  it("accepts well-formed full advisor info", () => {
    const result = validateAdvisorInfo({
      advisor_name: "王教授",
      advisor_email: "prof@nycu.edu.tw",
      advisor_nycu_id: "A0001",
    });
    expect(result.isValid).toBe(true);
    expect(result.errors).toEqual([]);
  });
});

// ─── validateBankInfo (14-digit postal account) ──────────────────────

describe("validateBankInfo", () => {
  it("rejects empty account number", () => {
    expect(validateBankInfo({}).isValid).toBe(false);
    expect(validateBankInfo({ account_number: "" }).isValid).toBe(false);
    expect(validateBankInfo({ account_number: "   " }).isValid).toBe(false);
  });

  it("requires exactly 14 digits (Taiwan postal account format)", () => {
    /* CRITICAL: Taiwan postal account is 14 digits. A 13/15-digit
     * number is a typo; a bank transfer to a malformed account number
     * silently fails on payment day. */
    expect(validateBankInfo({ account_number: "12345678901234" }).isValid).toBe(true); // 14
    expect(validateBankInfo({ account_number: "1234567890123" }).isValid).toBe(false); // 13
    expect(validateBankInfo({ account_number: "123456789012345" }).isValid).toBe(false); // 15
  });

  it("strips spaces and hyphens before counting digits", () => {
    /* Pin: '1234-5678-901234' and '12 34 5678 9012 34' both count as
     * 14 digits. UX-friendly — admins paste formatted account numbers
     * from email/Excel. */
    expect(validateBankInfo({ account_number: "1234-5678-901234" }).isValid).toBe(true);
    expect(validateBankInfo({ account_number: "12 34 5678 9012 34" }).isValid).toBe(true);
  });

  it("rejects non-digit characters even after stripping", () => {
    /* Pin: only digits + spaces/hyphens allowed. 'abcd' rejected
     * with 'numbers only' error (not the digit-count error). */
    const result = validateBankInfo({ account_number: "abcd1234567890" });
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("數字"))).toBe(true);
  });

  it("reports current digit count in error for mid-typing UX", () => {
    /* Pin: error message includes the user's current digit count so
     * the form-field can show 'X/14 digits' progress. */
    const result = validateBankInfo({ account_number: "1234567890" }); // 10 digits
    expect(result.isValid).toBe(false);
    expect(result.errors.some((e) => e.includes("10"))).toBe(true);
  });
});

// ─── sanitizeAdvisorEmail (empty → undefined sentinel) ───────────────

describe("sanitizeAdvisorEmail", () => {
  it("returns undefined for empty/null/whitespace", () => {
    /* CRITICAL: API contract treats `undefined` as 'unset', `''` as
     * 'set to empty string'. A refactor breaking this would send `''`
     * to the API → backend's `AdvisorInfoBase` validator (covered
     * separately) coerces it to None, but other endpoints might not. */
    expect(sanitizeAdvisorEmail("")).toBeUndefined();
    expect(sanitizeAdvisorEmail("   ")).toBeUndefined();
    expect(sanitizeAdvisorEmail(null)).toBeUndefined();
    expect(sanitizeAdvisorEmail(undefined)).toBeUndefined();
  });

  it("trims and returns valid email", () => {
    expect(sanitizeAdvisorEmail("  prof@nycu.edu.tw  ")).toBe("prof@nycu.edu.tw");
  });
});

// ─── sanitizeAdvisorInfo (composite sanitizer) ───────────────────────

describe("sanitizeAdvisorInfo", () => {
  it("trims all string fields", () => {
    const result = sanitizeAdvisorInfo({
      advisor_name: "  Prof Wang  ",
      advisor_email: "  p@nycu.edu.tw  ",
      advisor_nycu_id: "  A0001  ",
    });
    expect(result).toEqual({
      advisor_name: "Prof Wang",
      advisor_email: "p@nycu.edu.tw",
      advisor_nycu_id: "A0001",
    });
  });

  it("converts empty strings to undefined for all fields", () => {
    /* Pin: matches the sanitizeAdvisorEmail sentinel pattern for ALL
     * fields, not just email. Otherwise stale empty strings persist
     * in DB. */
    const result = sanitizeAdvisorInfo({
      advisor_name: "",
      advisor_email: "",
      advisor_nycu_id: "",
    });
    expect(result.advisor_name).toBeUndefined();
    expect(result.advisor_email).toBeUndefined();
    expect(result.advisor_nycu_id).toBeUndefined();
  });
});

// ─── sanitizeBankInfo (strip spaces + hyphens) ───────────────────────

describe("sanitizeBankInfo", () => {
  it("strips spaces and hyphens from account number", () => {
    /* Pin: canonical form is digits-only. '12-34 5678' → '12345678'.
     * Otherwise downstream DB lookups on partial matches fail. */
    expect(sanitizeBankInfo({ account_number: "1234-5678-901234" })).toEqual({
      account_number: "12345678901234",
    });
    expect(sanitizeBankInfo({ account_number: "12 34 5678 9012 34" })).toEqual({
      account_number: "12345678901234",
    });
  });

  it("returns undefined for empty/missing account_number", () => {
    expect(sanitizeBankInfo({}).account_number).toBeUndefined();
    expect(sanitizeBankInfo({ account_number: "" }).account_number).toBeUndefined();
    expect(sanitizeBankInfo({ account_number: "   " }).account_number).toBeUndefined();
  });
});
