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
// when it is selectable AND the student has not already submitted it. The
// backend computes `already_submitted` (see EligibleScholarshipResponse).
export function isApplyableScholarship(scholarship: ScholarshipType): boolean {
  return isSelectableScholarship(scholarship) && !scholarship.already_submitted;
}
