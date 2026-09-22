import { isDocumentUploadRequired } from "./application-helpers";

interface ProgressField {
  field_name: string;
  is_active: boolean;
  is_required: boolean;
  is_fixed?: boolean;
}

interface ProgressDocument {
  document_name: string;
  is_active: boolean;
  is_required: boolean;
  requires_upload?: boolean;
  is_fixed?: boolean;
}

export interface FormProgressInput {
  fields: ProgressField[];
  documents: ProgressDocument[];
  formData: Record<string, unknown>;
  fileData: Record<string, unknown[]>;
  hasSubTypeChoice: boolean;
  selectedSubTypeCount: number;
  // 指導教授資訊 + 郵局帳號 saved via「儲存個人資料」. Submission is blocked
  // until this is true, so it must count toward the bar — otherwise the bar
  // reads 100% while 提交申請 stays disabled.
  isPersonalInfoSaved: boolean;
}

const isFilled = (value: unknown): boolean =>
  value !== undefined && value !== null && value !== "";

export const calculateFormProgress = ({
  fields,
  documents,
  formData,
  fileData,
  hasSubTypeChoice,
  selectedSubTypeCount,
  isPersonalInfoSaved,
}: FormProgressInput): number => {
  const requiredFields = fields.filter(
    f => f.is_active && f.is_required && !f.is_fixed
  );
  const requiredDocuments = documents.filter(isDocumentUploadRequired);

  const completionChecks = [
    isPersonalInfoSaved,
    ...requiredFields.map(f => isFilled(formData[f.field_name])),
    ...requiredDocuments.map(d => (fileData[d.document_name]?.length ?? 0) > 0),
    ...(hasSubTypeChoice ? [selectedSubTypeCount > 0] : []),
  ];

  const completedItems = completionChecks.filter(Boolean).length;
  return Math.round((completedItems / completionChecks.length) * 100);
};
