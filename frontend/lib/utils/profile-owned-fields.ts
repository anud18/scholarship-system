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
 * The backend's export PDF collapses them the same way through
 * `PROFILE_OWNED_FIELD_SOURCES` in `backend/app/services/profile_owned_fields.py`.
 */
export const CANONICAL_ACCOUNT_FIELD_ID = "postal_account";
const ACCOUNT_FIELD_SYNONYMS = new Set([
  CANONICAL_ACCOUNT_FIELD_ID,
  "account_number",
]);

/** Collapse the 郵局帳號 synonyms onto one id; every other id is unchanged. */
export const canonicalizeFieldId = (fieldId: string): string =>
  ACCOUNT_FIELD_SYNONYMS.has(fieldId) ? CANONICAL_ACCOUNT_FIELD_ID : fieldId;

// Never rendered as form data: `files` is upload bookkeeping and `agree_terms`
// has its own consent row in the dialog.
const EXCLUDED_FIELD_IDS = new Set(["files", "agree_terms"]);

// The wizard folds the account the student typed into the submitted fields
// under this id. A `postal_account` copy may instead be another student's
// account leaked through the shared form-config prefill (#1443).
const OWN_ACCOUNT_FIELD_ID = "account_number";

// An application detail payload; typed loosely so both `Application` and the
// display component's looser form-data prop fit.
type ApplicationPayload = object | null | undefined;

const getSubmittedFields = (application: ApplicationPayload): Record<string, unknown> =>
  (application as { submitted_form_data?: { fields?: Record<string, unknown> } })
    ?.submitted_form_data?.fields || {};

const hasValue = (value: unknown): boolean =>
  value !== null && value !== undefined && value !== "";

const submittedValue = (fieldData: unknown): unknown =>
  fieldData && typeof fieldData === "object" && "value" in fieldData
    ? (fieldData as { value: unknown }).value
    : undefined;

/** What the student actually submitted, with the 郵局帳號 synonyms collapsed. */
export const collectSubmittedValues = (
  application: ApplicationPayload
): Record<string, unknown> => {
  const values: Record<string, unknown> = {};

  Object.entries(getSubmittedFields(application)).forEach(([fieldId, fieldData]) => {
    const value = submittedValue(fieldData);
    if (!hasValue(value)) return;
    if (EXCLUDED_FIELD_IDS.has(fieldId)) return;

    // Submissions may store the account under both synonyms. The student's own
    // `account_number` wins, whatever the JSON key order.
    const canonicalId = canonicalizeFieldId(fieldId);
    if (canonicalId in values && fieldId !== OWN_ACCOUNT_FIELD_ID) return;
    values[canonicalId] = value;
  });

  return values;
};

/**
 * The submitted values plus the fixed fields that live on the student's
 * UserProfile instead of `submitted_form_data`. This is what the review
 * dialog shows, so the staff editor starts from it too.
 *
 * Only fields the scholarship's own form config declares (`declaredFieldIds`)
 * are merged: the backend injects the 指導教授 trio only when the scholarship
 * requires professor review, and an application that never asked for those
 * fields must not sprout them from a profile filled in for another scholarship.
 */
export const withProfileOwnedFields = (
  submittedValues: Record<string, unknown>,
  application: ApplicationPayload,
  declaredFieldIds?: Readonly<Record<string, unknown>>
): Record<string, unknown> => {
  const values = { ...submittedValues };
  if (!declaredFieldIds) return values;

  const keepSubmittedAccount = hasValue(
    submittedValue(getSubmittedFields(application)[OWN_ACCOUNT_FIELD_ID])
  );
  Object.entries(collectProfileOwnedFieldValues(application)).forEach(
    ([fieldId, value]) => {
      if (!(fieldId in declaredFieldIds)) return;
      // The account the student submitted with this application stays.
      if (fieldId === CANONICAL_ACCOUNT_FIELD_ID && keepSubmittedAccount) return;
      // Otherwise the profile wins over a submitted copy: these fields belong on
      // the profile, and a copy in submitted_form_data may be another student's
      // values leaked through the shared form-config prefill (#1443). An empty
      // profile value was dropped already, so an imported application whose
      // profile lacks it keeps its own copy.
      values[fieldId] = value;
    }
  );

  return values;
};

/**
 * Pull the UserProfile-owned field values off an application detail payload.
 * Empty/missing values are dropped so the caller still renders「未填寫」for a
 * student who never filled the section in.
 */
export const collectProfileOwnedFieldValues = (
  application: ApplicationPayload
): Record<string, string> => {
  const values: Record<string, string> = {};
  if (!application) return values;

  Object.entries(PROFILE_OWNED_FIELD_SOURCES).forEach(
    ([fieldId, sourceKey]) => {
      const value = (application as Record<string, unknown>)[sourceKey];
      if (typeof value === "string" && value.trim() !== "") {
        values[fieldId] = value;
      }
    }
  );

  return values;
};
