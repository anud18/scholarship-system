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
