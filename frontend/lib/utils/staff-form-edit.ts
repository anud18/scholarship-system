import type { ApplicationField } from "@/lib/api";
import { ApplicationStatus } from "@/lib/enums";
import { PROFILE_OWNED_FIELD_SOURCES } from "@/lib/utils/profile-owned-fields";

/**
 * Statuses in which staff may not edit the submitted form. Mirrors
 * STAFF_FORM_EDIT_BLOCKED_STATUSES in backend/app/models/application.py: a
 * draft/returned form belongs to the student, the rest left the process.
 */
const STAFF_FORM_EDIT_BLOCKED_STATUSES: ReadonlySet<string> = new Set([
  ApplicationStatus.DRAFT,
  ApplicationStatus.RETURNED,
  ApplicationStatus.WITHDRAWN,
  ApplicationStatus.CANCELLED,
  ApplicationStatus.CANCELLED_BY_CHALLENGE,
  ApplicationStatus.DELETED,
]);

export const isStaffFormEditable = (status: string | null | undefined): boolean =>
  !!status && !STAFF_FORM_EDIT_BLOCKED_STATUSES.has(status);

const isProfileOwned = (field: ApplicationField): boolean =>
  field.field_name in PROFILE_OWNED_FIELD_SOURCES ||
  (!!field.fixed_key && field.fixed_key in PROFILE_OWNED_FIELD_SOURCES);

/** The submitted `fields[name].value` of each given field. */
export const getSubmittedFieldValues = (
  submittedFormData: Record<string, unknown> | null | undefined,
  fields: ApplicationField[]
): Record<string, unknown> => {
  const stored = (submittedFormData?.fields ?? {}) as Record<string, { value?: unknown } | null>;
  return Object.fromEntries(fields.map((field) => [field.field_name, stored[field.field_name]?.value]));
};

/** Active form-config fields minus 郵局帳號／指導教授, which live on the UserProfile. */
export const splitStaffEditableFields = (
  fields: ApplicationField[]
): { editable: ApplicationField[]; profileOwned: ApplicationField[] } => {
  const active = fields.filter((field) => field.is_active);
  return {
    editable: active.filter((field) => !isProfileOwned(field)),
    profileOwned: active.filter(isProfileOwned),
  };
};
