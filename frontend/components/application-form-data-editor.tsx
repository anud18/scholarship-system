"use client";

import { useMemo, useState, type ReactElement } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import api from "@/lib/api";
import type { Application, ApplicationField } from "@/lib/api";
import { fieldFormatError, isAdvisorField } from "@/lib/utils/staff-form-edit";

type Locale = "zh" | "en";

interface FieldInputProps {
  field: ApplicationField;
  value: unknown;
  onChange: (value: unknown) => void;
  locale: Locale;
  invalid: boolean;
}

interface ApplicationFormDataEditorProps {
  applicationId: number;
  editableFields: ApplicationField[];
  initialValues: Record<string, unknown>;
  locale: Locale;
  onSaved: (application: Application, message: string) => void;
  onCancel: () => void;
}

const asText = (value: unknown): string =>
  value === null || value === undefined ? "" : String(value);

const isBlank = (value: unknown): boolean =>
  value === null || value === undefined || (typeof value === "string" && value.trim() === "");

const sameValue = (a: unknown, b: unknown): boolean =>
  (isBlank(a) && isBlank(b)) || a === b;

const optionLabel = (
  option: { label: string; label_en?: string },
  locale: Locale
): string => (locale === "en" && option.label_en ? option.label_en : option.label);

const TextInput = ({ field, value, onChange, invalid }: FieldInputProps) => (
  <Input
    id={field.field_name}
    type={field.field_type === "email" ? "email" : "text"}
    value={asText(value)}
    maxLength={field.max_length}
    onChange={(e) => onChange(e.target.value)}
    aria-invalid={invalid || undefined}
  />
);

const FIELD_INPUTS: Record<string, (props: FieldInputProps) => ReactElement> = {
  text: TextInput,
  email: TextInput,
  textarea: ({ field, value, onChange, invalid }) => (
    <Textarea
      id={field.field_name}
      value={asText(value)}
      maxLength={field.max_length}
      rows={4}
      onChange={(e) => onChange(e.target.value)}
      aria-invalid={invalid || undefined}
    />
  ),
  number: ({ field, value, onChange, invalid }) => (
    <Input
      id={field.field_name}
      type="number"
      value={asText(value)}
      min={field.min_value}
      max={field.max_value}
      step={field.step_value}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      aria-invalid={invalid || undefined}
    />
  ),
  date: ({ field, value, onChange, invalid }) => (
    <Input
      id={field.field_name}
      type="date"
      value={asText(value)}
      onChange={(e) => onChange(e.target.value)}
      aria-invalid={invalid || undefined}
    />
  ),
  select: ({ field, value, onChange, locale }) => (
    <Select value={asText(value)} onValueChange={onChange}>
      <SelectTrigger id={field.field_name}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {field.field_options?.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {optionLabel(option, locale)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  ),
  radio: ({ field, value, onChange, locale }) => (
    <div className="space-y-2">
      {field.field_options?.map((option) => (
        <label key={option.value} className="flex items-center gap-2 text-sm">
          <input
            type="radio"
            name={field.field_name}
            value={option.value}
            checked={value === option.value}
            onChange={(e) => onChange(e.target.value)}
            className="h-4 w-4"
          />
          {optionLabel(option, locale)}
        </label>
      ))}
    </div>
  ),
  checkbox: ({ field, value, onChange }) => (
    <Checkbox
      id={field.field_name}
      checked={value === true}
      onCheckedChange={(checked) => onChange(checked === true)}
    />
  ),
};

export function ApplicationFormDataEditor({
  applicationId,
  editableFields,
  initialValues,
  locale,
  onSaved,
  onCancel,
}: ApplicationFormDataEditorProps) {
  const t = (zh: string, en: string) => (locale === "zh" ? zh : en);
  const [values, setValues] = useState<Record<string, unknown>>(initialValues);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputFields = useMemo(
    () => editableFields.filter((field) => field.field_type in FIELD_INPUTS),
    [editableFields]
  );

  const changedFields = useMemo(() => {
    const changed: Record<string, unknown> = {};
    inputFields.forEach(({ field_name }) => {
      if (!sameValue(values[field_name], initialValues[field_name])) {
        changed[field_name] = values[field_name];
      }
    });
    return changed;
  }, [inputFields, values, initialValues]);

  const fieldErrors: Record<string, string> = {};
  inputFields.forEach((field) => {
    if (!(field.field_name in changedFields)) return;
    const value = values[field.field_name];
    if (isBlank(value)) {
      if (field.is_required && field.field_type !== "checkbox") {
        fieldErrors[field.field_name] = t("此欄位為必填", "This field is required");
      }
      return;
    }
    const formatError = fieldFormatError(field, asText(value).trim());
    if (formatError) fieldErrors[field.field_name] = formatError;
  });

  const advisorFields = inputFields.filter(isAdvisorField);
  const lastAdvisorField = advisorFields[advisorFields.length - 1]?.field_name;

  const hasChanges = Object.keys(changedFields).length > 0;
  const canSave = hasChanges && Object.keys(fieldErrors).length === 0 && !isSaving;

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    try {
      const response = await api.applications.updateFormFields(applicationId, changedFields);
      if (!response.success || !response.data) {
        setError(response.message || t("儲存失敗", "Save failed"));
        return;
      }
      onSaved(response.data, response.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {inputFields.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {t("此獎學金沒有可修改的表單欄位", "This scholarship has no editable form fields")}
        </p>
      )}

      {inputFields.map((field) => {
        const FieldInput = FIELD_INPUTS[field.field_type];
        const fieldError = fieldErrors[field.field_name];
        return (
          <div key={field.field_name} className="space-y-1">
            <Label htmlFor={field.field_name}>
              {locale === "en" && field.field_label_en ? field.field_label_en : field.field_label}
              {field.is_required && <span className="ml-1 text-red-500">*</span>}
            </Label>
            <FieldInput
              field={field}
              value={values[field.field_name]}
              onChange={(value) => setValues((prev) => ({ ...prev, [field.field_name]: value }))}
              locale={locale}
              invalid={!!fieldError}
            />
            {fieldError && <p className="text-sm text-red-600">{fieldError}</p>}
            {field.field_name === lastAdvisorField && (
              <p className="text-sm text-muted-foreground">
                {t(
                  "指導教授資料存於學生個人資料，修改後會套用到該生的所有申請",
                  "Advisor details live on the student's profile; a change applies to all of the student's applications"
                )}
              </p>
            )}
          </div>
        );
      })}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>
          {t("取消", "Cancel")}
        </Button>
        <Button type="button" onClick={handleSave} disabled={!canSave}>
          {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t("儲存", "Save")}
        </Button>
      </div>
    </div>
  );
}
