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
    return locale === "zh"
      ? fieldLabels[fieldName].zh
      : fieldLabels[fieldName].en || fieldLabels[fieldName].zh || fieldName;
  }
  return formatFieldName(fieldName, locale);
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
  console.log("ApplicationFormDataDisplay received formData:", formData);

  useEffect(() => {
    const formatData = async () => {
      setIsLoading(true);
      const formatted: Record<string, any> = {};

      // 只處理 submitted_form_data.fields 結構
      // 這是學生在申請時填寫的表單欄位
      const dataToProcess: Record<string, any> = {};

      // 處理後端的 submitted_form_data.fields 結構
      if (formData.submitted_form_data && formData.submitted_form_data.fields) {
        // 後端嵌套結構 - 只處理欄位，不處理文件
        Object.entries(formData.submitted_form_data.fields).forEach(
          ([fieldId, fieldData]: [string, any]) => {
            if (
              fieldData &&
              typeof fieldData === "object" &&
              "value" in fieldData
            ) {
              const value = fieldData.value;
              // 跳過文件相關欄位和空值
              if (
                value &&
                value !== "" &&
                fieldId !== "files" &&
                fieldId !== "agree_terms"
              ) {
                dataToProcess[fieldId] = value;
              }
            }
          }
        );
      }
      // 注意：移除了其他的 fallback 邏輯
      // 表單內容應該只顯示 submitted_form_data.fields
      // 系統欄位（id, status, created_at 等）不應該在這裡顯示

      for (const [key, value] of Object.entries(dataToProcess)) {
        if (key === "scholarship_type") {
          try {
            formatted[key] = await formatFieldValue(key, value, locale);
          } catch (error) {
            console.warn(`Failed to format scholarship type: ${value}`, error);
            formatted[key] = value;
          }
        } else {
          formatted[key] = value;
        }
      }

      setFormattedData(formatted);
      setIsLoading(false);
    };

    formatData();
  }, [formData, locale]);

  if (isLoading) {
    // 處理載入狀態的顯示
    const dataToShow: Record<string, any> = {};

    if (formData.submitted_form_data && formData.submitted_form_data.fields) {
      // 後端嵌套結構 - 只處理欄位
      Object.entries(formData.submitted_form_data.fields).forEach(
        ([fieldId, fieldData]: [string, any]) => {
          if (
            fieldData &&
            typeof fieldData === "object" &&
            "value" in fieldData
          ) {
            const value = fieldData.value;
            if (
              value &&
              value !== "" &&
              fieldId !== "files" &&
              fieldId !== "agree_terms"
            ) {
              dataToShow[fieldId] = value;
            }
          }
        }
      );
    }

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
    </div>
  );
}
