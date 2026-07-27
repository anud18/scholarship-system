/**
 * The form-config fields that are NOT stored in `submitted_form_data`.
 *
 * `ApplicationFieldService.inject_fixed_fields` adds 郵局帳號 (`postal_account`)
 * and the 指導教授 trio (`advisor_*`) to every scholarship's form config, but the
 * application wizard collects them in a dedicated section that writes to the
 * student's UserProfile — they never become `submitted_form_data.fields` entries.
 * A form-data view that only reads the submitted fields therefore renders all
 * four as「未填寫」. The backend carries the authoritative values on the
 * application detail response (see `ApplicationResponse.postal_account` /
 * `.advisor_*`); this module maps them back onto their field ids.
 */

/** field id in the form config -> property on the application detail response. */
export const PROFILE_OWNED_FIELD_SOURCES: Readonly<Record<string, string>> = {
  postal_account: "postal_account",
  advisor_name: "advisor_name",
  advisor_email: "advisor_email",
  advisor_nycu_id: "advisor_nycu_id",
};

/**
 * The ids that carry the one 郵局帳號 a student typed — the form config calls it
 * `postal_account`, while the wizard folds the same value into the submitted
 * fields as `account_number` (for the bank-verification service). Both resolve
 * to the label 郵局帳號, so rendering them separately shows the field twice.
 * Mirrors `ACCOUNT_FIELD_SYNONYMS` in `backend/app/services/form_field_labels.py`.
 */
export const CANONICAL_ACCOUNT_FIELD_ID = "postal_account";
const ACCOUNT_FIELD_SYNONYMS = new Set([
  CANONICAL_ACCOUNT_FIELD_ID,
  "account_number",
]);

/** Collapse the 郵局帳號 synonyms onto one id; every other id is unchanged. */
export const canonicalizeFieldId = (fieldId: string): string =>
  ACCOUNT_FIELD_SYNONYMS.has(fieldId) ? CANONICAL_ACCOUNT_FIELD_ID : fieldId;

/**
 * Pull the UserProfile-owned field values off an application detail payload.
 * Empty/missing values are dropped so the caller still renders「未填寫」for a
 * student who never filled the section in.
 */
export const collectProfileOwnedFieldValues = (
  application: Record<string, unknown> | null | undefined
): Record<string, string> => {
  const values: Record<string, string> = {};
  if (!application) return values;

  Object.entries(PROFILE_OWNED_FIELD_SOURCES).forEach(
    ([fieldId, sourceKey]) => {
      const value = application[sourceKey];
      if (typeof value === "string" && value.trim() !== "") {
        values[fieldId] = value;
      }
    }
  );

  return values;
};
