import { Locale } from "@/lib/validators";
import { api } from "@/lib/api";
import { logger } from "@/lib/utils/logger";
import {
  ApplicationStatus,
  ReviewStage,
  getApplicationStatusLabel,
  getApplicationStatusBadgeVariant,
  getReviewStageLabel,
  getReviewStageBadgeVariant,
} from "@/lib/enums";

// Shape of document entries in `submitted_form_data.documents` from
// the backend. All fields optional because the upstream JSON can come
// from several sources (form_data, submitted_form_data, SIS upload).
interface DocumentPayload {
  file_id?: string | number;
  id?: string | number;
  filename?: string;
  original_filename?: string;
  file_size?: number;
  mime_type?: string;
  document_type?: string;
  file_type?: string;
  file_path?: string;
  download_url?: string;
  is_verified?: boolean;
  upload_time?: string;
  uploaded_at?: string;
  document_id?: string;
}


export type BadgeVariant = "secondary" | "default" | "outline" | "destructive";

// 時間軸步驟類型
export type TimelineStep = {
  id: string;
  title: string;
  status: "completed" | "current" | "pending" | "rejected";
  date: string;
};

// 格式化日期
export const formatDate = (
  dateString: string | null | undefined,
  locale: Locale
) => {
  if (!dateString) return "";
  const date = new Date(dateString);
  return date.toLocaleDateString(locale === "zh" ? "zh-TW" : "en-US");
};

// ReviewStage progression order for timeline
const REVIEW_STAGE_ORDER: { [key: string]: number } = {
  student_draft: 0,
  student_submitted: 1,
  professor_review: 2,
  professor_reviewed: 3,
  college_review: 4,
  college_reviewed: 5,
  college_ranking: 6,
  college_ranked: 7,
  admin_review: 8,
  admin_reviewed: 9,
  quota_distribution: 10,
  quota_distributed: 11,
  roster_preparation: 12,
  roster_prepared: 13,
  roster_submitted: 14,
  completed: 15,
  archived: 16,
};

// Helper to check if review_stage has progressed past a certain point
const hasReachedStage = (currentStage: string | undefined, targetStage: string): boolean => {
  if (!currentStage) return false;
  const currentOrder = REVIEW_STAGE_ORDER[currentStage] ?? -1;
  const targetOrder = REVIEW_STAGE_ORDER[targetStage] ?? -1;
  return currentOrder >= targetOrder;
};

// Structural shape consumed by the helpers below. Matches the canonical
// Application interface plus the review-stage extensions surfaced by the
// /applications/{id} backend response.
type ApplicationTimelineInput = {
  status: string;
  review_stage?: string;
  professor_reviews?: Array<{ reviewed_at?: string }>;
  application_reviews?: Array<{ review_stage?: string; reviewed_at?: string }>;
  professor?: { name?: string; nycu_id?: string };
  requires_professor_recommendation?: boolean;
  requires_college_review?: boolean;
  allow_college_view_distribution?: boolean;
  submitted_at?: string;
  created_at?: string;
  approved_at?: string;
  reviewed_at?: string;
};

// 獲取申請時間軸
export const getApplicationTimeline = (
  application: ApplicationTimelineInput,
  locale: Locale
): TimelineStep[] => {
  const status = application.status as ApplicationStatus;
  const reviewStage = application.review_stage as string | undefined;

  // 獲取教授審核資訊
  const professorReview = application.professor_reviews?.[0];
  const hasProfessorReview = Boolean(professorReview?.reviewed_at);

  // 獲取學院審核資訊
  const collegeReview = application.application_reviews?.find(
    (r: { review_stage?: string; reviewed_at?: string }) =>
      r.review_stage === "college_review"
  );
  const hasCollegeReview = Boolean(collegeReview?.reviewed_at);

  // 教授姓名
  const professorName = application.professor?.name || application.professor?.nycu_id;

  // 判斷合併步驟狀態的輔助函數:
  // entryStage 為進入此步驟的階段,exitStage 為此步驟完成時所到達的階段
  // (review_stage 達到 exitStage 即視為此步驟已完成)
  const getStepStatus = (
    entryStage: string,
    exitStage: string,
    hasCompletedEvidence?: boolean
  ): "completed" | "current" | "pending" | "rejected" => {
    // 如果被拒絕,且已達到該階段,標記為 rejected
    if (status === "rejected" && hasReachedStage(reviewStage, entryStage)) {
      return "rejected";
    }

    // 如果有明確的完成證據 (如審核記錄),或已進入後續階段
    if (hasCompletedEvidence || hasReachedStage(reviewStage, exitStage)) {
      return "completed";
    }

    // 已進入此步驟但尚未完成
    if (hasReachedStage(reviewStage, entryStage)) {
      return "current";
    }

    // 尚未達到
    return "pending";
  };

  // Workflow configuration flags
  const requiresProfessor = application.requires_professor_recommendation ?? false;
  const requiresCollege = application.requires_college_review ?? false;
  // 管理員「開放學院查看分發結果」開關:開啟後最終步驟才會打勾
  const allowCollegeViewDistribution = application.allow_college_view_distribution ?? false;

  const isTerminated =
    status === "rejected" ||
    status === "returned" ||
    status === "withdrawn" ||
    status === "cancelled" ||
    status === "cancelled_by_challenge";

  const steps: TimelineStep[] = [
    // 1. 提交申請
    {
      id: "submit",
      title: locale === "zh" ? "提交申請" : "Submit Application",
      status: reviewStage === "student_draft" ? "current" : "completed",
      date: reviewStage === "student_draft"
        ? ""
        : formatDate(application.submitted_at || application.created_at, locale),
    },
  ];

  // 2. 教授審核 (only if required)
  if (requiresProfessor) {
    steps.push({
      id: "professor_review",
      title: locale === "zh"
        ? `教授審核${professorName ? ` (${professorName})` : ""}`
        : `Professor Review${professorName ? ` (${professorName})` : ""}`,
      status: getStepStatus("student_submitted", "professor_reviewed", hasProfessorReview),
      date: hasProfessorReview ? formatDate(professorReview?.reviewed_at, locale) : "",
    });
  }

  // 3. 學院審核 (only if required)
  if (requiresCollege) {
    steps.push({
      id: "college_review",
      title: locale === "zh" ? "學院審核" : "College Review",
      status: getStepStatus(
        requiresProfessor ? "professor_reviewed" : "student_submitted",
        "college_reviewed",
        hasCollegeReview
      ),
      date: hasCollegeReview ? formatDate(collegeReview?.reviewed_at, locale) : "",
    });
  }

  // 4. 已核定(請洽院辦) — 僅在管理員開放學院查看分發結果後才打勾
  steps.push({
    id: "final_decision",
    title: locale === "zh" ? "已核定(請洽院辦)" : "Finalized (Contact College Office)",
    status: isTerminated
      ? "rejected"
      : status === "approved"
        ? allowCollegeViewDistribution
          ? "completed"
          : "current"
        : "pending",
    date: isTerminated
      ? formatDate(application.reviewed_at, locale)
      : status === "approved" && allowCollegeViewDistribution
        ? formatDate(application.approved_at, locale)
        : "",
  });

  return steps;
};


// 判斷是否應該顯示階段狀態 (ReviewStage)
export const shouldShowReviewStage = (
  status: string,
  reviewStage?: string
): boolean => {
  // 如果沒有 review_stage,不顯示
  if (!reviewStage) return false;

  // 草稿狀態不顯示階段
  if (status === "draft") return false;

  // 最終狀態(已核准/已拒絕等)可以選擇不顯示詳細階段
  const finalStatuses = ["approved", "rejected", "withdrawn", "cancelled", "deleted"];

  // 可根據需求調整:最終狀態是否仍顯示階段
  // return !finalStatuses.includes(status);

  // 目前策略:所有非草稿狀態都顯示階段
  return true;
};

// 獲取顯示狀態 - 返回狀態和階段的組合資訊
export const getDisplayStatusInfo = (
  application: { status: string; review_stage?: string },
  locale: Locale
): {
  showStatus: boolean;
  showStage: boolean;
  statusLabel: string;
  stageLabel: string;
  statusVariant: BadgeVariant;
  stageVariant: BadgeVariant;
} => {
  const status = application.status as ApplicationStatus;
  const reviewStage = application.review_stage;

  // 獲取階段標籤和 variant
  let stageLabel = "";
  let stageVariant: BadgeVariant = "outline";

  if (reviewStage) {
    try {
      // 將 string 轉換為 ReviewStage enum
      const stageEnum = reviewStage as ReviewStage;
      stageLabel = getReviewStageLabel(stageEnum, locale);
      stageVariant = getReviewStageBadgeVariant(stageEnum);
    } catch (error) {
      // 如果轉換失敗,使用原始值
      stageLabel = reviewStage;
    }
  }

  return {
    showStatus: true, // 狀態永遠顯示
    showStage: shouldShowReviewStage(application.status, reviewStage),
    statusLabel: getApplicationStatusLabel(status, locale),
    stageLabel,
    statusVariant: getApplicationStatusBadgeVariant(status),
    stageVariant,
  };
};


// 格式化欄位名稱
export const formatFieldName = (fieldName: string, locale: Locale) => {
  const fieldNameMap: { [key: string]: string } = {
    academic_year: locale === "zh" ? "學年度" : "Academic Year",
    semester: locale === "zh" ? "學期" : "Semester",
    gpa: locale === "zh" ? "學期平均成績" : "GPA",
    class_ranking_percent:
      locale === "zh" ? "班級排名百分比" : "Class Ranking %",
    dept_ranking_percent:
      locale === "zh" ? "系所排名百分比" : "Department Ranking %",
    completed_terms: locale === "zh" ? "已修學期數" : "Completed Terms",
    contact_phone: locale === "zh" ? "聯絡電話" : "Contact Phone",
    contact_email: locale === "zh" ? "聯絡信箱" : "Contact Email",
    contact_address: locale === "zh" ? "通訊地址" : "Contact Address",
    bank_account: locale === "zh" ? "銀行帳戶" : "Bank Account",
    account_number: locale === "zh" ? "郵局帳號" : "Post Office Account",
    research_proposal: locale === "zh" ? "研究計畫" : "Research Proposal",
    budget_plan: locale === "zh" ? "預算規劃" : "Budget Plan",
    milestone_plan: locale === "zh" ? "里程碑規劃" : "Milestone Plan",
    expected_graduation_date:
      locale === "zh" ? "預計畢業日期" : "Expected Graduation Date",
    personal_statement: locale === "zh" ? "個人陳述" : "Personal Statement",
    scholarship_type: locale === "zh" ? "獎學金類型" : "Scholarship Type",
  };
  return fieldNameMap[fieldName] || fieldName;
};

// 格式化欄位值（從資料庫獲取獎學金類型名稱）
/**
 * Render a form-field value as a human-readable string. Used by the
 * application-form-data-display component to show dynamic-form data
 * collected from students.
 *
 * Why:
 * - String/number/boolean: use `String(value)` (handles 0, false, etc.).
 * - null/undefined: return empty string (caller decides placeholder).
 * - Array: comma-separated stringified items (matches the array-test
 *   contract from PR #244 and the eye-test of "hobbies: reading, coding").
 * - Plain object: JSON.stringify so nested data renders as readable JSON
 *   instead of the default `[object Object]`. (Replaces TODO at
 *   `application-form-data-display.test.tsx:215`.)
 *
 * Truncation is the caller's responsibility — different render paths
 * use different cap lengths.
 */
export const formatDisplayValue = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatDisplayValue(item)).join(", ");
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
};

export const formatFieldValue = async (
  fieldName: string,
  value: unknown,
  locale: Locale
) => {
  if (fieldName === "scholarship_type") {
    try {
      // 先嘗試從所有獎學金中查找對應的 code
      const response = await api.scholarships.getAll();
      if (response.success && response.data) {
        const scholarship = response.data.find(s => s.code === value);
        if (scholarship) {
          return locale === "zh"
            ? scholarship.name
            : scholarship.name_en || scholarship.name;
        }
      }
    } catch (error) {
      logger.warn("Failed to fetch scholarship type for code", {
        code: value,
        error,
      });
    }
    // API 失敗時直接顯示 code
    return value;
  }
  return value;
};

// 獲取文件標籤（使用動態標籤或後備靜態標籤）
export const getDocumentLabel = (
  docType: string,
  locale: Locale,
  dynamicLabel?: { zh?: string; en?: string }
) => {
  // 如果有動態標籤，優先使用
  if (dynamicLabel) {
    return locale === "zh"
      ? dynamicLabel.zh
      : dynamicLabel.en || dynamicLabel.zh || docType;
  }

  // 後備靜態標籤（僅在無法獲取動態標籤時使用）
  const docTypeMap = {
    zh: {
      transcript: "成績單",
      research_proposal: "研究計畫書",
      budget_plan: "預算計畫",
      bank_account: "銀行帳戶證明",
      bank_account_proof: "存摺封面",
      recommendation_letter: "推薦信",
      cv: "履歷表",
      portfolio: "作品集",
      certificate: "證書",
      other: "其他文件",
    },
    en: {
      transcript: "Academic Transcript",
      research_proposal: "Research Proposal",
      budget_plan: "Budget Plan",
      bank_account: "Bank Account Verification",
      bank_account_proof: "Bank Book Cover",
      recommendation_letter: "Recommendation Letter",
      cv: "CV/Resume",
      portfolio: "Portfolio",
      certificate: "Certificate",
      other: "Other Documents",
    },
  };
  return docTypeMap[locale][docType as keyof typeof docTypeMap.zh] || docType;
};

// 獲取申請文件
export const fetchApplicationFiles = async (applicationId: number) => {
  try {
    // 從申請詳情獲取文件，現在文件資訊整合在 submitted_form_data.documents 中
    const appResponse =
      await api.applications.getApplicationById(applicationId);
    if (
      appResponse.success &&
      appResponse.data?.submitted_form_data?.documents
    ) {
      // 將 documents 轉換為 ApplicationFile 格式以保持向後兼容
      return appResponse.data.submitted_form_data.documents.map((doc: DocumentPayload) => ({
        id: doc.file_id,
        filename: doc.filename,
        original_filename: doc.original_filename,
        file_size: doc.file_size,
        mime_type: doc.mime_type,
        file_type: doc.document_type,
        file_path: doc.file_path,
        download_url: doc.download_url,
        is_verified: doc.is_verified,
        uploaded_at: doc.upload_time,
      }));
    }

    // 如果申請詳情沒有文件，嘗試專門的文件API（向後兼容）
    const filesResponse =
      await api.applications.getApplicationFiles(applicationId);
    if (filesResponse.success && filesResponse.data) {
      return filesResponse.data;
    }

    return [];
  } catch (error) {
    logger.error("Failed to fetch application files", { error });
    return [];
  }
};

// Shape of a single entry inside `submitted_form_data.fields`.
export interface SubmittedFormFieldValue {
  field_id: string;
  field_type: string;
  value: string;
  required: boolean;
}

/**
 * Build the `submitted_form_data.fields` map sent when a student submits an
 * application.
 *
 * Why: the applicant's post-office account (郵局帳號, 限本人) is collected in a
 * dedicated wizard section and persisted to the user profile, but the admin
 * review dialog and the backend bank-verification service both read the
 * account number from the application's `submitted_form_data.fields`
 * (see backend `extract_bank_fields_from_application`, which looks up the
 * `account_number` key). If it is omitted here the account never reaches the
 * admin side, so we always fold it into the form fields.
 */
// Taiwan mobile number: pure digits, starts with 09, exactly 10 digits.
// Mirrors the backend contact_phone validation so client and server agree.
export const TAIWAN_MOBILE_PATTERN = /^09\d{8}$/;
export const TAIWAN_MOBILE_MESSAGE = "請輸入本人有效的台灣手機 (09xxxxxx)";

export const isValidTaiwanMobile = (value: unknown): boolean =>
  typeof value === "string" && TAIWAN_MOBILE_PATTERN.test(value);

export const buildApplicationFormFields = (
  dynamicFormData: Record<string, unknown>,
  accountNumber?: string | null
): Record<string, SubmittedFormFieldValue> => {
  const fields: Record<string, SubmittedFormFieldValue> = {};

  Object.entries(dynamicFormData).forEach(([fieldName, value]) => {
    fields[fieldName] = {
      field_id: fieldName,
      field_type: "text",
      value: String(value),
      required: true,
    };
  });

  const trimmedAccount = accountNumber?.trim();
  if (trimmedAccount) {
    fields.account_number = {
      field_id: "account_number",
      field_type: "text",
      value: trimmedAccount,
      required: true,
    };
  }

  return fields;
};

// Admin-configurable document visibility (see application_documents.display_in_list
// / requires_upload). `!== false` keeps pre-flag API payloads behaving as before.
export const isDocumentListedInScholarshipCard = (doc: {
  is_active: boolean;
  display_in_list?: boolean;
}): boolean => doc.is_active && doc.display_in_list !== false;

export const isDocumentUploadRequired = (doc: {
  is_active: boolean;
  is_required: boolean;
  requires_upload?: boolean;
  is_fixed?: boolean;
}): boolean =>
  doc.is_active && doc.is_required && doc.requires_upload !== false && !doc.is_fixed;
