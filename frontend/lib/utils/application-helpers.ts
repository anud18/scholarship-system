import { Locale } from "@/lib/validators";
import { api } from "@/lib/api";

// 申請狀態類型
export type ApplicationStatus =
  | "draft"
  | "submitted"
  | "under_review"
  | "pending_recommendation"
  | "recommended"
  | "approved"
  | "rejected"
  | "returned"
  | "withdrawn"
  | "cancelled";
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

// Workflow status groupings for timeline rendering
const WAIT_PROFESSOR_CURRENT_STATUSES = new Set<string>([
  "submitted",
  "pending_review",
]);

const WAIT_PROFESSOR_COMPLETED_STATUSES = new Set<string>([
  "pending_recommendation",
  "professor_review_pending",
  "professor_reviewed",
  "recommended",
  "college_review_pending",
  "college_reviewed",
  "under_review",
  "approved",
  "rejected",
  "returned",
  "withdrawn",
  "cancelled",
  "pending",
  "completed",
]);

const PROFESSOR_REVIEW_CURRENT_STATUSES = new Set<string>([
  "pending_recommendation",
  "professor_review_pending",
]);

const PROFESSOR_REVIEW_COMPLETED_STATUSES = new Set<string>([
  "professor_reviewed",
  "recommended",
  "college_review_pending",
  "college_reviewed",
  "under_review",
  "approved",
  "rejected",
  "returned",
  "withdrawn",
  "cancelled",
  "pending",
  "completed",
]);

const PROFESSOR_REVIEW_SUBMITTED_STATUSES = new Set<string>([
  "professor_reviewed",
  "recommended",
  "college_review_pending",
  "college_reviewed",
  "under_review",
  "approved",
  "rejected",
  "returned",
  "withdrawn",
  "cancelled",
  "pending",
  "completed",
]);

const WAIT_COLLEGE_CURRENT_STATUSES = new Set<string>([
  "professor_reviewed",
  "recommended",
  "college_review_pending",
]);

const WAIT_COLLEGE_COMPLETED_STATUSES = new Set<string>([
  "college_reviewed",
  "under_review",
  "approved",
  "rejected",
  "returned",
  "withdrawn",
  "cancelled",
  "pending",
  "completed",
]);

const COLLEGE_REVIEW_CURRENT_STATUSES = new Set<string>([
  "college_review_pending",
  "under_review",
]);

const COLLEGE_REVIEW_COMPLETED_STATUSES = new Set<string>([
  "college_reviewed",
  "approved",
  "rejected",
  "returned",
  "withdrawn",
  "cancelled",
  "pending",
  "completed",
]);

const COLLEGE_SUBMITTED_COMPLETED_STATUSES = new Set<string>([
  "college_reviewed",
  "approved",
  "rejected",
  "returned",
  "withdrawn",
  "cancelled",
  "pending",
  "completed",
]);

const FINAL_DECISION_COMPLETED_STATUSES = new Set<string>([
  "approved",
  "completed",
]);

const FINAL_DECISION_REJECTED_STATUSES = new Set<string>([
  "rejected",
  "returned",
  "withdrawn",
  "cancelled",
]);

// 獲取申請時間軸
export const getApplicationTimeline = (
  application: any,
  locale: Locale
): TimelineStep[] => {
  const status = application.status as string;

  // 獲取教授審核資訊
  const professorReview = application.professor_reviews?.[0];
  const hasProfessorReview = Boolean(professorReview?.reviewed_at);

  // 獲取學院審核資訊
  const collegeReview = application.application_reviews?.find(
    (r: any) => r.review_stage === "college_review"
  );
  const hasCollegeReview = Boolean(collegeReview?.reviewed_at);

  // 教授姓名
  const professorName = application.professor?.name || application.professor?.nycu_id;

  const steps: TimelineStep[] = [
    // 1. 提交申請
    {
      id: "submit",
      title: locale === "zh" ? "提交申請" : "Submit Application",
      status: status === "draft" ? "current" : "completed",
      date:
        status === "draft"
          ? ""
          : formatDate(
              application.submitted_at || application.created_at,
              locale
            ),
    },

    // 2. 等待教授審核
    {
      id: "wait_professor",
      title:
        locale === "zh"
          ? `等待教授審核${professorName ? ` (${professorName})` : ""}`
          : `Waiting for Professor Review${professorName ? ` (${professorName})` : ""}`,
      status:
        status === "draft"
          ? "pending"
          : WAIT_PROFESSOR_CURRENT_STATUSES.has(status)
            ? "current"
            : WAIT_PROFESSOR_COMPLETED_STATUSES.has(status)
              ? "completed"
              : "pending",
      date: "",
    },

    // 3. 教授審核中
    {
      id: "professor_reviewing",
      title: locale === "zh" ? "教授審核中" : "Professor Reviewing",
      status:
        PROFESSOR_REVIEW_CURRENT_STATUSES.has(status)
          ? "current"
          : hasProfessorReview || PROFESSOR_REVIEW_COMPLETED_STATUSES.has(status)
            ? "completed"
            : "pending",
      date: "",
    },

    // 4. 教授已送出審核
    {
      id: "professor_submitted",
      title: locale === "zh" ? "教授已送出審核" : "Professor Review Submitted",
      status:
        hasProfessorReview || PROFESSOR_REVIEW_SUBMITTED_STATUSES.has(status)
          ? "completed"
          : "pending",
      date: hasProfessorReview ? formatDate(professorReview.reviewed_at, locale) : "",
    },

    // 5. 等待學院審核
    {
      id: "wait_college",
      title: locale === "zh" ? "等待學院審核" : "Waiting for College Review",
      status:
        WAIT_COLLEGE_CURRENT_STATUSES.has(status)
          ? "current"
          : WAIT_COLLEGE_COMPLETED_STATUSES.has(status)
            ? "completed"
            : "pending",
      date: "",
    },

    // 6. 學院審核中
    {
      id: "college_reviewing",
      title: locale === "zh" ? "學院審核中" : "College Reviewing",
      status:
        COLLEGE_REVIEW_CURRENT_STATUSES.has(status)
          ? "current"
          : hasCollegeReview || COLLEGE_REVIEW_COMPLETED_STATUSES.has(status)
            ? "completed"
            : "pending",
      date: "",
    },

    // 7. 學院已送出審核
    {
      id: "college_submitted",
      title: locale === "zh" ? "學院已送出審核" : "College Review Submitted",
      status:
        hasCollegeReview || COLLEGE_SUBMITTED_COMPLETED_STATUSES.has(status)
          ? "completed"
          : "pending",
      date: hasCollegeReview ? formatDate(collegeReview.reviewed_at, locale) : "",
    },

    // 8. 最終核定
    {
      id: "final_decision",
      title: locale === "zh" ? "最終核定" : "Final Decision",
      status:
        FINAL_DECISION_COMPLETED_STATUSES.has(status)
          ? "completed"
          : FINAL_DECISION_REJECTED_STATUSES.has(status)
            ? "rejected"
            : "pending",
      date:
        FINAL_DECISION_COMPLETED_STATUSES.has(status)
          ? formatDate(application.approved_at, locale)
          : FINAL_DECISION_REJECTED_STATUSES.has(status)
            ? formatDate(application.reviewed_at, locale)
            : "",
    },
  ];

  return steps;
};

// 獲取狀態顏色
export const getStatusColor = (status: ApplicationStatus): BadgeVariant => {
  const statusMap: Record<ApplicationStatus, BadgeVariant> = {
    draft: "secondary",
    submitted: "default",
    under_review: "outline",
    pending_recommendation: "outline",
    recommended: "outline",
    approved: "default",
    rejected: "destructive",
    returned: "secondary",
    withdrawn: "secondary",
    cancelled: "secondary",
  };
  return statusMap[status];
};

// 獲取狀態名稱
export const getStatusName = (status: ApplicationStatus, locale: Locale) => {
  const statusNames = {
    zh: {
      draft: "草稿",
      submitted: "已提交",
      under_review: "審核中",
      pending_recommendation: "待教授推薦",
      recommended: "已推薦",
      approved: "已核准",
      rejected: "已拒絕",
      returned: "已退回",
      withdrawn: "已撤回",
      cancelled: "已取消",
    },
    en: {
      draft: "Draft",
      submitted: "Submitted",
      under_review: "Under Review",
      pending_recommendation: "Pending Recommendation",
      recommended: "Recommended",
      approved: "Approved",
      rejected: "Rejected",
      returned: "Returned",
      withdrawn: "Withdrawn",
      cancelled: "Cancelled",
    },
  } as const;
  return statusNames[locale][status];
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
export const formatFieldValue = async (
  fieldName: string,
  value: any,
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
      console.warn(
        `Failed to fetch scholarship type for code: ${value}`,
        error
      );
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
      return appResponse.data.submitted_form_data.documents.map((doc: any) => ({
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
    console.error("Failed to fetch application files:", error);
    return [];
  }
};
