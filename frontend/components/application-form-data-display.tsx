"use client";

import { useState, useEffect } from "react";
import { Label } from "@/components/ui/label";
import { Locale } from "@/lib/validators";
import {
  formatFieldName,
  formatFieldValue,
} from "@/lib/utils/application-helpers";

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
    console.log(
      `🏷️ Found label for "${fieldName}":`,
      label,
      "from:",
      fieldLabels[fieldName]
    );
    return label;
  }
  const fallbackLabel = formatFieldName(fieldName, locale);
  console.log(
    `🏷️ No label found for "${fieldName}", using fallback:`,
    fallbackLabel
  );
  return fallbackLabel;
};

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

export function ApplicationFormDataDisplay({
  formData,
  locale,
  fieldLabels,
}: ApplicationFormDataDisplayProps) {
  const [formattedData, setFormattedData] = useState<Record<string, any>>({});
  const [isLoading, setIsLoading] = useState(true);

  // Debug logging

    console.log(
    "📋 fields 是物件:",
    typeof formData?.submitted_form_data?.fields === "object"
  );
  console.log(
    "📋 fields 鍵值:",
    formData?.submitted_form_data?.fields
      ? Object.keys(formData.submitted_form_data.fields)
      : "N/A"
  );
  console.log(
    "📋 原始 fields 物件:",
    formData?.submitted_form_data?.fields
  );
  console.log("🏷️ 接收到的 fieldLabels:", fieldLabels);
  console.log(
    "🏷️ fieldLabels 鍵值:",
    fieldLabels ? Object.keys(fieldLabels) : "沒有標籤"
  );


    if (formData?.submitted_form_data) {

  }

  useEffect(() => {
    const formatData = async () => {
      setIsLoading(true);
      const formatted: Record<string, any> = {};

      // 只處理新格式：submitted_form_data.fields
      const fields = formData?.submitted_form_data?.fields || {};


      console.log("🔄 Processing fields:", fields);
      console.log("🔄 Fields entries count:", Object.entries(fields).length);
      console.log("🔄 All field keys:", Object.keys(fields));

      for (const [fieldId, fieldData] of Object.entries(fields)) {
        if (
          fieldData &&
          typeof fieldData === "object" &&
          "value" in fieldData
        ) {
          const value = (fieldData as any).value;

          // 跳過空值、files 欄位和 agree_terms
          if (
            value !== null &&
            value !== undefined &&
            value !== "" &&
            fieldId !== "files" &&
            fieldId !== "agree_terms"
          ) {
            if (fieldId === "scholarship_type") {
              try {
                formatted[fieldId] = await formatFieldValue(
                  fieldId,
                  value,
                  locale
                );
              } catch (error) {
                console.warn(
                  `Failed to format scholarship type: ${value}`,
                  error
                );
                formatted[fieldId] = value;
              }
            } else {
              formatted[fieldId] = value;
            }
          }
        }
      }

      console.log("✅ Formatted data:", formatted);
      setFormattedData(formatted);
      setIsLoading(false);
    };

    formatData();
  }, [formData, locale]);

  if (isLoading) {
    // 處理載入狀態的顯示
    const dataToShow: Record<string, any> = {};
    const fields = formData?.submitted_form_data?.fields || {};

    Object.entries(fields).forEach(([fieldId, fieldData]: [string, any]) => {
      if (fieldData && typeof fieldData === "object" && "value" in fieldData) {
        const value = fieldData.value;
        if (
          value !== null &&
          value !== undefined &&
          value !== "" &&
          fieldId !== "files" &&
          fieldId !== "agree_terms"
        ) {
          dataToShow[fieldId] = value;
        }
      }
    });

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
                    : typeof value === "string" && value.length > 100
                      ? `${value.substring(0, 100)}...`
                      : String(value)}
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
                {typeof value === "string" && value.length > 100
                  ? `${value.substring(0, 100)}...`
                  : String(value)}
              </p>
            </div>
          </div>
        );
      })}

      {/* 顯示 fieldLabels 中存在但 formattedData 中沒有值的字段 */}
      {fieldLabels && Object.entries(fieldLabels).map(([fieldName, labels]) => {
        // 如果這個字段已經在 formattedData 中，跳過
        if (fieldName in formattedData) {
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
