/**
 * Tests for the pure helpers exported alongside `useStudentProfile`
 * in `frontend/hooks/use-student-profile.ts`.
 *
 * Functions covered:
 *  - `hasCompleteProfile(profile)` — boolean gate for the "you must
 *    complete your profile before submitting" warning banner.
 *  - `getProfileCompletion(profile)` — 0-100 percentage rendered on the
 *    profile-progress ring on the student dashboard.
 *  - `getStudentDisplayName(studentInfo, userInfo)` — the name shown in
 *    the top-right user menu and on every student card.
 *
 * Regressions in these helpers cause:
 *  - The "incomplete profile" banner shows forever even after the
 *    student fills everything → support tickets.
 *  - Profile-progress ring stuck at 80% / 0% / 100% inappropriately.
 *  - Top-right menu shows "-" instead of the student's name (CLAUDE.md
 *    UX standard: never show "-" if a usable name exists).
 *
 * 16 cases. Pure jest.
 */

import {
  getProfileCompletion,
  getStudentDisplayName,
  hasCompleteProfile,
} from "../use-student-profile";

// ─── hasCompleteProfile ──────────────────────────────────────────────

describe("hasCompleteProfile", () => {
  it("returns false for null (no profile yet)", () => {
    expect(hasCompleteProfile(null)).toBe(false);
  });

  it("returns true when all four required fields are non-empty", () => {
    /* Pin: the gate is the conjunction of advisor_name +
     * advisor_email + advisor_nycu_id + account_number. Don't widen
     * silently — bank_document_photo_url is intentionally NOT here
     * (it only contributes to the percentage). */
    expect(
      hasCompleteProfile({
        advisor_name: "王教授",
        advisor_email: "advisor@nycu.edu.tw",
        advisor_nycu_id: "A00001",
        account_number: "12345678901234",
      })
    ).toBe(true);
  });

  it("returns false when any required field is missing", () => {
    expect(
      hasCompleteProfile({
        advisor_name: "王教授",
        advisor_email: "advisor@nycu.edu.tw",
        advisor_nycu_id: "A00001",
        // account_number missing
      })
    ).toBe(false);
  });

  it("returns false when any required field is empty string", () => {
    /* Pin: '' counts as not filled. Otherwise an unset form input
     * that posted as '' would silently mark profile complete. */
    expect(
      hasCompleteProfile({
        advisor_name: "王教授",
        advisor_email: "",
        advisor_nycu_id: "A00001",
        account_number: "12345678901234",
      })
    ).toBe(false);
  });

  it("returns false when any required field is null", () => {
    expect(
      hasCompleteProfile({
        advisor_name: "王教授",
        advisor_email: "advisor@nycu.edu.tw",
        advisor_nycu_id: null as unknown as string,
        account_number: "12345678901234",
      })
    ).toBe(false);
  });

  it("ignores extra unrelated fields", () => {
    /* Pin: arbitrary extra keys (e.g. bank_document_photo_url, id)
     * must not interfere — only the four required fields gate. */
    expect(
      hasCompleteProfile({
        advisor_name: "王教授",
        advisor_email: "advisor@nycu.edu.tw",
        advisor_nycu_id: "A00001",
        account_number: "12345678901234",
        id: 42,
        user_id: 7,
        bank_document_photo_url: undefined,
      })
    ).toBe(true);
  });
});

// ─── getProfileCompletion ────────────────────────────────────────────

describe("getProfileCompletion", () => {
  it("returns 0 for null profile", () => {
    expect(getProfileCompletion(null)).toBe(0);
  });

  it("returns 0 for empty profile", () => {
    expect(getProfileCompletion({})).toBe(0);
  });

  it("returns 100 when all five tracked fields are filled", () => {
    /* Pin: percentage is over FIVE fields (the four required + the
     * bank document URL). hasCompleteProfile() can be true at 80%
     * because bank_document_photo_url is optional for the gate but
     * contributes to the percentage. */
    expect(
      getProfileCompletion({
        advisor_name: "王教授",
        advisor_email: "advisor@nycu.edu.tw",
        advisor_nycu_id: "A00001",
        account_number: "12345678901234",
        bank_document_photo_url: "/uploads/bank.pdf",
      })
    ).toBe(100);
  });

  it("returns 80 when the four required are filled but no bank doc", () => {
    /* Pin: this exact value (80%) is rendered on the dashboard and
     * users learn it as the "ready but optional bank doc missing"
     * state. A regression that flipped the denominator (e.g. used 4
     * instead of 5) would silently break that signal. */
    expect(
      getProfileCompletion({
        advisor_name: "王教授",
        advisor_email: "advisor@nycu.edu.tw",
        advisor_nycu_id: "A00001",
        account_number: "12345678901234",
      })
    ).toBe(80);
  });

  it("rounds to nearest integer", () => {
    /* Pin: Math.round usage means 1/5 → 20, 2/5 → 40 etc. — exact
     * multiples of 20. No fractional %. */
    expect(getProfileCompletion({ advisor_name: "王教授" })).toBe(20);
    expect(
      getProfileCompletion({
        advisor_name: "王",
        advisor_email: "a@b",
      })
    ).toBe(40);
    expect(
      getProfileCompletion({
        advisor_name: "王",
        advisor_email: "a@b",
        advisor_nycu_id: "A1",
      })
    ).toBe(60);
  });

  it("treats empty string the same as missing", () => {
    expect(
      getProfileCompletion({
        advisor_name: "王",
        advisor_email: "",
        advisor_nycu_id: "A1",
      })
    ).toBe(40);
  });
});

// ─── getStudentDisplayName ───────────────────────────────────────────

describe("getStudentDisplayName", () => {
  it("prefers SIS student name (std_cname) over user_info.name", () => {
    /* Pin: SIS name is the authoritative Chinese name (CLAUDE.md §7
     * student_data snapshot). user_info.name is often the SSO email
     * prefix or English transliteration — less preferred for UI. */
    expect(
      getStudentDisplayName(
        { std_cname: "王小明" },
        { id: "1", nycu_id: "310460031", name: "wang.xiaoming", email: "x@y" }
      )
    ).toBe("王小明");
  });

  it("falls back to user_info.name when std_cname is missing", () => {
    expect(
      getStudentDisplayName(null, {
        id: "1",
        nycu_id: "X",
        name: "Wang",
        email: "x@y",
      })
    ).toBe("Wang");
  });

  it("falls back to user_info.name when studentInfo has no std_cname", () => {
    /* Pin: presence of studentInfo without std_cname must still
     * trigger the user_info fallback (otherwise staff users with no
     * SIS data would render "-"). */
    expect(
      getStudentDisplayName(
        { std_stdcode: "X" },
        { id: "1", nycu_id: "X", name: "Wang", email: "x@y" }
      )
    ).toBe("Wang");
  });

  it("returns '-' when both sources are absent", () => {
    /* Pin: '-' sentinel matches the table-cell convention used by
     * other helpers (e.g. getStudyingStatusName). */
    expect(getStudentDisplayName(null, null)).toBe("-");
  });

  it("returns '-' when std_cname is empty string and user_info.name is empty", () => {
    /* Pin: empty string is "not present" — must not render as a
     * blank cell. */
    expect(
      getStudentDisplayName(
        { std_cname: "" },
        { id: "1", nycu_id: "X", name: "", email: "x@y" }
      )
    ).toBe("-");
  });
});
