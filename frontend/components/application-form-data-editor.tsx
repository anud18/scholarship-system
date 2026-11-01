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
import {
  isValidTaiwanMobile,
  TAIWAN_MOBILE_MESSAGE,
} from "@/lib/utils/application-helpers";

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
  /** Form-config definitions, already narrowed to the staff-editable ones. */
  fields: ApplicationField[];
  /** Submitted values by field_name. */
  initialValues: Record<string, unknown>;
  locale: Locale;
  onSaved: (application: Application) => void;
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

// One input per field_type the backend accepts (staff_form_edit.FIELD_CODECS).
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
  fields,
  initialValues,
  locale,
  onSaved,
  onCancel,
}: ApplicationFormDataEditorProps) {
  const t = (zh: string, en: string) => (locale === "zh" ? zh : en);
  const [values, setValues] = useState<Record<string, unknown>>(initialValues);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const editableFields = useMemo(
    () => fields.filter((field) => field.field_type in FIELD_INPUTS),
    [fields]
  );

  const changedFields = useMemo(() => {
    const changed: Record<string, unknown> = {};
    editableFields.forEach(({ field_name }) => {
      if (!sameValue(values[field_name], initialValues[field_name])) {
        changed[field_name] = values[field_name];
      }
    });
    return changed;
  }, [editableFields, values, initialValues]);

  const fieldErrors: Record<string, string> = {};
  editableFields.forEach((field) => {
    const value = values[field.field_name];
    const isChanged = field.field_name in changedFields;
    if (field.is_required && field.field_type !== "checkbox" && isChanged && isBlank(value)) {
      fieldErrors[field.field_name] = t("此欄位為必填", "This field is required");
    } else if (
      field.field_name === "contact_phone" &&
      isChanged &&
      !isBlank(value) &&
      !isValidTaiwanMobile(asText(value).trim())
    ) {
      fieldErrors[field.field_name] = TAIWAN_MOBILE_MESSAGE;
    }
  });

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
      onSaved(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {editableFields.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {t("此獎學金沒有可修改的表單欄位", "This scholarship has no editable form fields")}
        </p>
      )}

      {editableFields.map((field) => {
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
