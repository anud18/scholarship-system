import type { ScholarshipType } from "@/lib/api/types";

export function isSelectableScholarship(scholarship: ScholarshipType): boolean {
  const hasCommonErrors =
    scholarship.errors?.some(rule => !rule.sub_type) || false;
  return (
    Array.isArray(scholarship.eligible_sub_types) &&
    scholarship.eligible_sub_types.length > 0 &&
    !hasCommonErrors
  );
}

// Apply-flow predicate: a scholarship is offered in the student apply flow only
// when it is selectable, the student has not already submitted it, AND it is
// still within its application period. The backend computes `already_submitted`
// and `is_application_period` (see EligibleScholarshipResponse). Effective-but-
// closed (生效但已截止) scholarships are selectable/visible but not applyable.
export function isApplyableScholarship(scholarship: ScholarshipType): boolean {
  return (
    isSelectableScholarship(scholarship) &&
    !scholarship.already_submitted &&
    scholarship.is_application_period !== false
  );
}

// The sub-types a student can actually pick. `general` is a synthetic
// catch-all (it matches no quota slot at distribution) and a null value is a
// placeholder, so neither counts as a real choice. Every place that decides
// whether sub-type selection is required — selector rendering, progress,
// auto-select, submit — must use this one predicate, or a list such as
// ["general", "nstc"] hides the selector while progress still demands a pick.
export function getRealSubTypes(
  scholarship: Pick<ScholarshipType, "eligible_sub_types"> | null | undefined
): NonNullable<ScholarshipType["eligible_sub_types"]> {
  return (scholarship?.eligible_sub_types ?? []).filter(
    st => Boolean(st.value) && st.value !== "general"
  );
}
