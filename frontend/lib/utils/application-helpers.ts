import { Locale } from "@/lib/validators";
import { api } from "@/lib/api";
import {
  ApplicationStatus,
  ReviewStage,
  getApplicationStatusLabel,
  getApplicationStatusBadgeVariant,
  getReviewStageLabel,
  getReviewStageBadgeVariant,
} from "@/lib/enums";

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

// 獲取申請時間軸
export const getApplicationTimeline = (
  application: any,
  locale: Locale
): TimelineStep[] => {
  const status = application.status as ApplicationStatus;
  const reviewStage = application.review_stage as string | undefined;

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

  // 判斷步驟狀態的輔助函數
  const getStepStatus = (
    targetStage: string,
    nextStage: string,
    hasCompletedEvidence?: boolean
  ): "completed" | "current" | "pending" | "rejected" => {
    // 如果被拒絕,且已達到該階段,標記為 rejected
    if (status === "rejected" && hasReachedStage(reviewStage, targetStage)) {
      return "rejected";
    }

    // 如果有明確的完成證據 (如審核記錄)
    if (hasCompletedEvidence) {
      return "completed";
    }

    // 如果已達到下一階段,則此階段已完成
    if (hasReachedStage(reviewStage, nextStage)) {
      return "completed";
    }

    // 如果正好在此階段
    if (reviewStage === targetStage) {
      return "current";
    }

    // 尚未達到
    return "pending";
  };

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

    // 2. 等待教授審核
    {
      id: "wait_professor",
      title: locale === "zh"
        ? `等待教授審核${professorName ? ` (${professorName})` : ""}`
        : `Waiting for Professor Review${professorName ? ` (${professorName})` : ""}`,
      status: getStepStatus("student_submitted", "professor_review"),
      date: "",
    },

    // 3. 教授審核中
    {
      id: "professor_reviewing",
      title: locale === "zh" ? "教授審核中" : "Professor Reviewing",
      status: getStepStatus("professor_review", "professor_reviewed", hasProfessorReview),
      date: "",
    },

    // 4. 教授已送出審核
    {
      id: "professor_submitted",
      title: locale === "zh" ? "教授已送出審核" : "Professor Review Submitted",
      status: getStepStatus("professor_reviewed", "college_review", hasProfessorReview),
      date: hasProfessorReview ? formatDate(professorReview.reviewed_at, locale) : "",
    },

    // 5. 等待學院審核
    {
      id: "wait_college",
      title: locale === "zh" ? "等待學院審核" : "Waiting for College Review",
      status: getStepStatus("professor_reviewed", "college_review"),
      date: "",
    },

    // 6. 學院審核中
    {
      id: "college_reviewing",
      title: locale === "zh" ? "學院審核中" : "College Reviewing",
      status: getStepStatus("college_review", "college_reviewed", hasCollegeReview),
      date: "",
    },

    // 7. 學院已送出審核
    {
      id: "college_submitted",
      title: locale === "zh" ? "學院已送出審核" : "College Review Submitted",
      status: getStepStatus("college_reviewed", "admin_review", hasCollegeReview),
      date: hasCollegeReview ? formatDate(collegeReview.reviewed_at, locale) : "",
    },

    // 8. 最終核定
    {
      id: "final_decision",
      title: locale === "zh" ? "最終核定" : "Final Decision",
      status:
        status === "approved"
          ? "completed"
          : status === "rejected" || status === "returned" || status === "withdrawn" || status === "cancelled"
            ? "rejected"
            : "pending",
      date:
        status === "approved"
          ? formatDate(application.approved_at, locale)
          : status === "rejected" || status === "returned" || status === "withdrawn" || status === "cancelled"
            ? formatDate(application.reviewed_at, locale)
            : "",
    },
  ];

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
  application: any,
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
