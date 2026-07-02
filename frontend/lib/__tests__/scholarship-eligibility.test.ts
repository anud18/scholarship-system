/**
 * Tests for `lib/scholarship-eligibility.ts:isSelectableScholarship`.
 *
 * This predicate decides whether a scholarship card on the student
 * dashboard is selectable (shows "Apply" button) or grayed out. Wrong
 * verdict either:
 * - Hides scholarships students COULD apply for (functional bug, the
 *   student misses the deadline thinking they're ineligible).
 * - Shows scholarships students CAN'T apply for (clicks lead to a
 *   confusing 422 from backend).
 *
 * The contract: a scholarship is selectable iff
 *   eligible_sub_types is a non-empty array AND
 *   there's no top-level (sub_type-less) error rule.
 *
 * 7 cases.
 */
import type { ScholarshipType } from "@/lib/api/types";
import {
  isApplyableScholarship,
  isSelectableScholarship,
} from "../scholarship-eligibility";

// Minimal ScholarshipType shape — only the fields the predicate reads.
type _Sch = {
  id?: number;
  code?: string;
  eligible_sub_types?: string[];
  errors?: Array<{ sub_type?: string | null; rule_id?: number }>;
};

const scholarship = (s: _Sch) => s as unknown as Parameters<typeof isSelectableScholarship>[0];

describe("isSelectableScholarship", () => {
  it("returns true when eligible_sub_types is non-empty and no common errors", () => {
    /** Happy path — at least one sub-type passes all gates. */
    expect(
      isSelectableScholarship(
        scholarship({ eligible_sub_types: ["nstc", "moe_1w"], errors: [] }),
      ),
    ).toBe(true);
  });

  it("returns false when eligible_sub_types is empty array", () => {
    /** No sub-type passed → no application path → not selectable. */
    expect(
      isSelectableScholarship(scholarship({ eligible_sub_types: [], errors: [] })),
    ).toBe(false);
  });

  it("returns false when eligible_sub_types is undefined", () => {
    /** Defensive: missing field treated same as empty (not selectable).
     * Pin so a backend regression that drops the field doesn't silently
     * make all scholarships appear selectable. */
    expect(isSelectableScholarship(scholarship({ errors: [] }))).toBe(false);
  });

  it("returns false when eligible_sub_types is not an array (defensive)", () => {
    /** If the backend ships a malformed payload (string instead of array),
     * the Array.isArray guard prevents .length crash. */
    expect(
      isSelectableScholarship(
        scholarship({ eligible_sub_types: "nstc" as never, errors: [] }),
      ),
    ).toBe(false);
  });

  it("returns false when a common (sub_type-less) error rule exists", () => {
    /** Errors without sub_type apply to ALL sub-types — student can't
     * proceed even if some sub-types appear eligible. The check is
     * `.sub_type` falsy (undefined OR null OR ''). */
    const sch = scholarship({
      eligible_sub_types: ["nstc"],
      errors: [{ sub_type: undefined, rule_id: 1 }],
    });
    expect(isSelectableScholarship(sch)).toBe(false);
  });

  it("returns true when errors exist but ALL have a sub_type (per-track)", () => {
    /** Per-sub-type errors don't block the whole scholarship — student
     * just has fewer tracks. Pin so partial-eligibility scholarships
     * still show as selectable. */
    const sch = scholarship({
      eligible_sub_types: ["nstc"],
      errors: [{ sub_type: "moe_1w", rule_id: 1 }],
    });
    expect(isSelectableScholarship(sch)).toBe(true);
  });

  it("returns false when errors is undefined and eligible_sub_types is empty", () => {
    /** Combined edge case: missing errors AND empty sub_types. The
     * `|| false` shortcircuit in `hasCommonErrors` prevents undefined
     * propagating into the final boolean. */
    expect(
      isSelectableScholarship(scholarship({ eligible_sub_types: [] })),
    ).toBe(false);
  });
});

const applyableSelectable = {
  eligible_sub_types: [
    { value: "nstc", label: "NSTC", label_en: "NSTC", is_default: true },
  ],
  errors: [],
} as unknown as ScholarshipType;

describe("isApplyableScholarship", () => {
  it("is true for a selectable scholarship with no submission", () => {
    expect(isSelectableScholarship(applyableSelectable)).toBe(true);
    expect(isApplyableScholarship(applyableSelectable)).toBe(true);
  });

  it("is false when already submitted", () => {
    const submitted = {
      ...applyableSelectable,
      already_submitted: true,
    } as ScholarshipType;
    expect(isApplyableScholarship(submitted)).toBe(false);
  });

  it("is true when already_submitted is explicitly false", () => {
    const notSubmitted = {
      ...applyableSelectable,
      already_submitted: false,
    } as ScholarshipType;
    expect(isApplyableScholarship(notSubmitted)).toBe(true);
  });

  it("is false when not selectable, even if not submitted", () => {
    const notSelectable = {
      eligible_sub_types: [],
      errors: [],
      already_submitted: false,
    } as unknown as ScholarshipType;
    expect(isApplyableScholarship(notSelectable)).toBe(false);
  });

  it("is false when the application period has closed (生效但已截止)", () => {
    /** Effective-but-closed scholarships stay selectable/visible (read-only)
     * but must NOT be offered in the apply flow. Pin so a regression can't let
     * students start applications after the deadline. */
    const closed = {
      ...applyableSelectable,
      already_submitted: false,
      is_application_period: false,
    } as ScholarshipType;
    expect(isSelectableScholarship(closed)).toBe(true);
    expect(isApplyableScholarship(closed)).toBe(false);
  });

  it("is true when is_application_period is explicitly true", () => {
    const open = {
      ...applyableSelectable,
      already_submitted: false,
      is_application_period: true,
    } as ScholarshipType;
    expect(isApplyableScholarship(open)).toBe(true);
  });
});
