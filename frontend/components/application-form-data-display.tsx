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

/**
 * The values to show for one application: the submitted dynamic fields (with the
 * 郵局帳號 synonyms collapsed onto one id) plus the fixed fields that live on the
 * student's UserProfile instead of `submitted_form_data`. Without the second
 * source, 郵局帳號 renders twice (once filled, once「未填寫」) and the whole
 * 指導教授 section renders as「未填寫」— see `profile-owned-fields.ts`.
 */
const collectDisplayValues = (
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

  Object.entries(
    collectProfileOwnedFieldValues(formData as Record<string, unknown>)
  ).forEach(([fieldId, value]) => {
    // A submitted snapshot wins over the current profile: it is what the
    // student sent with this application.
    if (!(fieldId in values)) values[fieldId] = value;
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
      const formatted = collectDisplayValues(formData);

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
  }, [formData, locale]);

  if (isLoading) {
    // 處理載入狀態的顯示（scholarship_type 尚未解析成名稱）
    const dataToShow = collectDisplayValues(formData);

    // 如果沒有表單資料，顯示訊息
    if (Object.keys(dataToShow).length === 0) {
      return (
        <div className="text-center py-8">
          <p className="text-sm text-muted-foreground">
            {locale === "zh" ? "無表單資料" : "No form data"}
          </p>
        </div>
      );
    }

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
                  {key === "scholarship_type"
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
      </div>
    );
  }

  // 如果沒有表單資料，顯示訊息
  if (Object.keys(formattedData).length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-muted-foreground">
          {locale === "zh" ? "無表單資料" : "No form data"}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {Object.entries(formattedData).map(([key, value]) => {
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
                {(() => {
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

      {/* 顯示 fieldLabels 中存在但 formattedData 中沒有值的字段 */}
      {fieldLabels && Object.entries(fieldLabels).map(([fieldName]) => {
        // 如果這個字段已經在 formattedData 中，跳過（郵局帳號的同義 id 也算）
        if (canonicalizeFieldId(fieldName) in formattedData) {
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
