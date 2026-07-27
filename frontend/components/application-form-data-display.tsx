"use client";

import { useState, useEffect } from "react";
import { Label } from "@/components/ui/label";
import { Locale } from "@/lib/validators";
import { logger } from "@/lib/utils/logger";
import {
  formatDisplayValue,
  formatFieldName,
  formatFieldValue,
} from "@/lib/utils/application-helpers";
import {
  canonicalizeFieldId,
  collectProfileOwnedFieldValues,
} from "@/lib/utils/profile-owned-fields";

interface ApplicationFormDataDisplayProps {
  formData:
    | Record<string, any>
    | {
        form_data?: Record<string, any>;
        submitted_form_data?: Record<string, any>;
        fields?: Record<string, any>;
      };
  locale: Locale;
  fieldLabels?: { [key: string]: { zh?: string; en?: string } };
}

// Never rendered as form data: `files` is upload bookkeeping and `agree_terms`
// has its own consent row in the dialog.
const EXCLUDED_FIELD_IDS = new Set(["files", "agree_terms"]);

/** What the student actually submitted, with the 郵局帳號 synonyms collapsed. */
const collectSubmittedValues = (
  formData: ApplicationFormDataDisplayProps["formData"]
): Record<string, unknown> => {
  const values: Record<string, unknown> = {};
  const fields =
    (formData as { submitted_form_data?: { fields?: Record<string, unknown> } })
      ?.submitted_form_data?.fields || {};

  Object.entries(fields).forEach(([fieldId, fieldData]) => {
    if (!fieldData || typeof fieldData !== "object" || !("value" in fieldData)) {
      return;
    }
    const value = (fieldData as { value: unknown }).value;
    if (value === null || value === undefined || value === "") return;
    if (EXCLUDED_FIELD_IDS.has(fieldId)) return;

    // Older submissions store the account under both synonyms; keep the first
    // one so the rendered value doesn't depend on JSON key order.
    const canonicalId = canonicalizeFieldId(fieldId);
    if (canonicalId in values) return;
    values[canonicalId] = value;
  });

  return values;
};

/**
 * The submitted values plus the fixed fields that live on the student's
 * UserProfile instead of `submitted_form_data` — without them 郵局帳號 renders
 * twice (once filled, once「未填寫」) and the 指導教授 block renders entirely as
 * 「未填寫」. See `profile-owned-fields.ts`.
 *
 * Only fields the scholarship's own form config declares (`fieldLabels`) are
 * merged: the backend injects the 指導教授 trio only when the scholarship
 * requires professor review, and an application that never asked for those
 * fields must not sprout them from a profile filled in for another scholarship.
 */
const withProfileOwnedFields = (
  submittedValues: Record<string, unknown>,
  formData: ApplicationFormDataDisplayProps["formData"],
  fieldLabels?: ApplicationFormDataDisplayProps["fieldLabels"]
): Record<string, unknown> => {
  const values = { ...submittedValues };
  if (!fieldLabels) return values;

  Object.entries(
    collectProfileOwnedFieldValues(formData as Record<string, unknown>)
  ).forEach(([fieldId, value]) => {
    if (!(fieldId in fieldLabels)) return;
    // A submitted snapshot wins over the current profile: it is what the
    // student sent with this application.
    if (fieldId in values) return;
    values[fieldId] = value;
  });

  return values;
};

// 獲取欄位標籤（優先使用動態標籤，後備使用靜態標籤）
const getFieldLabel = (
  fieldName: string,
  locale: Locale,
  fieldLabels?: { [key: string]: { zh?: string; en?: string } }
) => {
  if (fieldLabels && fieldLabels[fieldName]) {
    const label = locale === "zh"
      ? fieldLabels[fieldName].zh
      : fieldLabels[fieldName].en || fieldLabels[fieldName].zh || fieldName;
    logger.debug(
      `🏷️ Found label for "${fieldName}":`,
      label,
      "from:",
      fieldLabels[fieldName]
    );
    return label;
  }
  const fallbackLabel = formatFieldName(fieldName, locale);
  logger.debug(
    `🏷️ No label found for "${fieldName}", using fallback:`,
    fallbackLabel
  );
  return fallbackLabel;
};

export function ApplicationFormDataDisplay({
  formData,
  locale,
  fieldLabels,
}: ApplicationFormDataDisplayProps) {
  const [formattedData, setFormattedData] = useState<Record<string, any>>({});
  const [isLoading, setIsLoading] = useState(true);

  logger.debug(
    "🏷️ fieldLabels 鍵值:",
    fieldLabels ? Object.keys(fieldLabels) : "沒有標籤"
  );

  useEffect(() => {
    const formatData = async () => {
      setIsLoading(true);
      const formatted = withProfileOwnedFields(
        collectSubmittedValues(formData),
        formData,
        fieldLabels
      );

      // scholarship_type stores the code — resolve it to the scholarship's name.
      if (formatted.scholarship_type !== undefined) {
        try {
          formatted.scholarship_type = await formatFieldValue(
            "scholarship_type",
            formatted.scholarship_type,
            locale
          );
        } catch (error) {
          logger.warn(
            `Failed to format scholarship type: ${formatted.scholarship_type}`,
            error
          );
        }
      }

      logger.debug("✅ Formatted data:", formatted);
      setFormattedData(formatted);
      setIsLoading(false);
    };

    formatData();
  }, [formData, locale, fieldLabels]);

  const submittedValues = collectSubmittedValues(formData);

  // 「無表單資料」只看學生送出的欄位：UserProfile 來源的固定欄位是補充資訊，
  // 有 profile 不代表這份申請填過表單。
  if (Object.keys(submittedValues).length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-muted-foreground">
          {locale === "zh" ? "無表單資料" : "No form data"}
        </p>
      </div>
    );
  }

  // 載入中時先顯示未解析的值（scholarship_type 仍在查名稱）。
  const dataToShow = isLoading
    ? withProfileOwnedFields(submittedValues, formData, fieldLabels)
    : formattedData;

  return (
    <div className="space-y-3">
      {Object.entries(dataToShow).map(([key, value]) => {
        return (
          <div
            key={key}
            className="flex items-start justify-between p-3 bg-slate-50 rounded-lg"
          >
            <div className="flex-1">
              <Label className="text-sm font-medium text-gray-700">
                {getFieldLabel(key, locale, fieldLabels)}
              </Label>
              <p className="text-sm text-gray-600 mt-1">
                {isLoading && key === "scholarship_type"
                  ? "載入中..."
                  : (() => {
                      const rendered = formatDisplayValue(value);
                      return rendered.length > 100
                        ? `${rendered.substring(0, 100)}...`
                        : rendered;
                    })()}
              </p>
            </div>
          </div>
        );
      })}

      {/* 顯示 fieldLabels 中存在但 dataToShow 中沒有值的字段 */}
      {fieldLabels && Object.entries(fieldLabels).map(([fieldName]) => {
        // 如果這個字段已經顯示過，跳過（郵局帳號的同義 id 也算）
        if (canonicalizeFieldId(fieldName) in dataToShow) {
          return null;
        }

        // 顯示未填寫的字段
        return (
          <div
            key={fieldName}
            className="flex items-start justify-between p-3 bg-gray-100 rounded-lg opacity-60"
          >
            <div className="flex-1">
              <Label className="text-sm font-medium text-gray-500">
                {getFieldLabel(fieldName, locale, fieldLabels)}
              </Label>
              <p className="text-sm text-gray-400 mt-1 italic">
                {locale === "zh" ? "未填寫" : "Not filled"}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
