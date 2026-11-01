import type { ApplicationField } from "@/lib/api";
import { ApplicationStatus } from "@/lib/enums";
import {
  isValidTaiwanMobile,
  TAIWAN_MOBILE_MESSAGE,
} from "@/lib/utils/application-helpers";
import {
  canonicalizeFieldId,
  collectSubmittedValues,
  withProfileOwnedFields,
} from "@/lib/utils/profile-owned-fields";

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

const ADVISOR_FIELD_KEYS: ReadonlySet<string> = new Set([
  "advisor_name",
  "advisor_email",
  "advisor_nycu_id",
]);

export const POSTAL_ACCOUNT_DIGITS = 14;

// Mirrors validate_postal_account_format in backend/app/utils/bank_account_fields.py.
export const postalAccountError = (value: string): string | null => {
  const digits = value.replace(/\D/g, "").length;
  return digits === POSTAL_ACCOUNT_DIGITS
    ? null
    : `郵局帳號必須為 ${POSTAL_ACCOUNT_DIGITS} 位數字，目前為 ${digits} 位`;
};

const FIELD_FORMAT_RULES: Readonly<Record<string, (value: string) => string | null>> = {
  contact_phone: (value) => (isValidTaiwanMobile(value) ? null : TAIWAN_MOBILE_MESSAGE),
  postal_account: postalAccountError,
};

// Built-in fields are matched by fixed_key first, as the backend routes them.
const fieldKey = (field: ApplicationField): string => field.fixed_key || field.field_name;

export const isAdvisorField = (field: ApplicationField): boolean =>
  ADVISOR_FIELD_KEYS.has(fieldKey(field));

/** The format error for a filled-in value, or null when the field has no format rule or passes it. */
export const fieldFormatError = (field: ApplicationField, value: string): string | null =>
  FIELD_FORMAT_RULES[fieldKey(field)]?.(value) ?? null;

export const getStaffEditableFields = (fields: ApplicationField[]): ApplicationField[] =>
  fields.filter((field) => field.is_active);

/** The values the review dialog shows for these fields, keyed by field name. */
export const getEffectiveFieldValues = (
  application: object | null | undefined,
  fields: ApplicationField[]
): Record<string, unknown> => {
  const declared = Object.fromEntries(fields.map((field) => [field.field_name, true]));
  const effective = withProfileOwnedFields(
    collectSubmittedValues(application),
    application,
    declared
  );
  return Object.fromEntries(
    fields.map((field) => [field.field_name, effective[canonicalizeFieldId(field.field_name)]])
  );
};
