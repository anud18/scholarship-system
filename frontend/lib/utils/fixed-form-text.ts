/**
 * Text of the built-in ("fixed") items in the application wizard's 個人資料
 * section.
 *
 * 審核管理 lets an admin edit the 固定欄位 / 固定文件 (郵局帳號, 指導教授
 * trio, 存摺封面): 顯示名稱, 提示文字, 說明文字 and the document's 文件說明.
 * The edit is a `fixed_key` row that `ApplicationFieldService.inject_fixed_fields`
 * serves back inside the form config, but the wizard renders that section
 * from its own i18n table rather than from `DynamicApplicationForm` (which
 * skips `is_fixed` items), so the edit never reached the student. This
 * resolver maps the config rows back onto the wizard's strings.
 *
 * A row present in the config wins outright: it was pre-filled from the
 * built-in text when the admin opened it, so a blank 提示文字 / 說明文字 is a
 * deliberate clearing, not a gap. Only the label keeps a fallback, because a
 * field cannot render without one. `defaults` is the offline fallback for a
 * config that failed to load.
 */

import type { ScholarshipFormConfig } from "@/lib/api/types";

/** `fixed_key` values minted by `backend/app/services/application_field_service.py`. */
export const FIXED_FIELD_KEYS = [
  "postal_account",
  "advisor_name",
  "advisor_email",
  "advisor_nycu_id",
] as const;
export type FixedFieldKey = (typeof FIXED_FIELD_KEYS)[number];

export const FIXED_DOCUMENT_KEY_BANK_STATEMENT = "bank_statement";

/**
 * Whether the 存摺封面 must be uploaded before 儲存個人資料 / 提交申請.
 * Mirrors `ApplicationFieldService.is_fixed_bank_document_required`: the
 * built-in document is required, and only the admin's `bank_statement` row
 * can relax it. The backend always injects that row into the form config
 * and drops it again for students when the admin deactivated it, so a
 * loaded config without the row means "switched off"; a config that has
 * not loaded (or failed) keeps the built-in default.
 */
export const isFixedBankDocumentRequired = (
  config: Pick<ScholarshipFormConfig, "documents"> | null | undefined
): boolean => {
  if (!config) return true;
  const bankRow = config.documents?.find(
    doc => doc.fixed_key === FIXED_DOCUMENT_KEY_BANK_STATEMENT
  );
  if (!bankRow) return false;
  return bankRow.is_active && bankRow.is_required;
};

export interface FixedFieldText {
  label: string;
  placeholder: string;
  helpText: string;
}

export interface FixedDocumentText {
  label: string;
  description: string;
}

export interface FixedFormText {
  fields: Record<FixedFieldKey, FixedFieldText>;
  bankDocument: FixedDocumentText;
}

type Locale = "zh" | "en";

/** The row's value for `locale` (en falls back to zh), trimmed; "" when blank. */
const pickLocalized = (
  locale: Locale,
  zh: string | null | undefined,
  en: string | null | undefined
): string => {
  const preferred = locale === "en" ? en || zh : zh;
  return preferred?.trim() ?? "";
};

/**
 * Overlay the admin-edited fixed-item text from `config` onto `defaults`.
 * A missing config yields `defaults`; a key with no row keeps its default.
 */
export const resolveFixedFormText = (
  config: Pick<ScholarshipFormConfig, "fields" | "documents"> | null | undefined,
  locale: Locale,
  defaults: FixedFormText
): FixedFormText => {
  if (!config) return defaults;

  const fields = Object.fromEntries(
    FIXED_FIELD_KEYS.map(key => {
      const row = config.fields?.find(field => field.fixed_key === key);
      const fallback = defaults.fields[key];
      if (!row) return [key, fallback];
      return [
        key,
        {
          label:
            pickLocalized(locale, row.field_label, row.field_label_en) ||
            fallback.label,
          placeholder: pickLocalized(
            locale,
            row.placeholder,
            row.placeholder_en
          ),
          helpText: pickLocalized(locale, row.help_text, row.help_text_en),
        },
      ];
    })
  ) as Record<FixedFieldKey, FixedFieldText>;

  const bankRow = config.documents?.find(
    doc => doc.fixed_key === FIXED_DOCUMENT_KEY_BANK_STATEMENT
  );
  const bankDocument: FixedDocumentText = bankRow
    ? {
        label:
          pickLocalized(locale, bankRow.document_name, bankRow.document_name_en) ||
          defaults.bankDocument.label,
        description: pickLocalized(
          locale,
          bankRow.description,
          bankRow.description_en
        ),
      }
    : defaults.bankDocument;

  return { fields, bankDocument };
};
