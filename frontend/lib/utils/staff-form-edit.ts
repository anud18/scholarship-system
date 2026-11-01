import type { ApplicationField } from "@/lib/api";
import { ApplicationStatus } from "@/lib/enums";
import { PROFILE_OWNED_FIELD_SOURCES } from "@/lib/utils/profile-owned-fields";

const STUDENT_OWNED_FORM_STATUSES = [ApplicationStatus.DRAFT, ApplicationStatus.RETURNED];
const CLOSED_APPLICATION_STATUSES = [
  ApplicationStatus.WITHDRAWN,
  ApplicationStatus.CANCELLED,
  ApplicationStatus.CANCELLED_BY_CHALLENGE,
  ApplicationStatus.DELETED,
];
const STAFF_FORM_EDIT_BLOCKED_STATUSES: ReadonlySet<string> = new Set([
  ...STUDENT_OWNED_FORM_STATUSES,
  ...CLOSED_APPLICATION_STATUSES,
]);

export const isStaffFormEditable = (status: string | null | undefined): boolean =>
  !!status && !STAFF_FORM_EDIT_BLOCKED_STATUSES.has(status);

const isProfileOwned = (field: ApplicationField): boolean =>
  field.field_name in PROFILE_OWNED_FIELD_SOURCES ||
  (!!field.fixed_key && field.fixed_key in PROFILE_OWNED_FIELD_SOURCES);

export const getSubmittedFieldValues = (
  submittedFormData: Record<string, unknown> | null | undefined,
  fields: ApplicationField[]
): Record<string, unknown> => {
  const stored = (submittedFormData?.fields ?? {}) as Record<string, { value?: unknown } | null>;
  return Object.fromEntries(fields.map((field) => [field.field_name, stored[field.field_name]?.value]));
};

export const splitStaffEditableFields = (
  fields: ApplicationField[]
): { editable: ApplicationField[]; profileOwned: ApplicationField[] } => {
  const active = fields.filter((field) => field.is_active);
  return {
    editable: active.filter((field) => !isProfileOwned(field)),
    profileOwned: active.filter(isProfileOwned),
  };
};
