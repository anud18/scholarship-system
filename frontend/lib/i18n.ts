export type Locale = "zh" | "en"

export const defaultLocale: Locale = "zh"

export const locales: Locale[] = ["zh", "en"]

export const translations = {
  zh: {
    // 系統標題
    system: {
      title: "獎學金申請與簽核作業管理系統",
      subtitle: "Scholarship Application and Approval Management System",
      name: "SAMS",
    },

    // 導航
    nav: {
      dashboard: "儀表板",
      applications: "學生申請",
      review: "審核管理",
      admin: "系統管理",
      profile: "個人資料",
      logout: "登出",
    },

    // 個人資料管理
    profile_management: {
      title: "個人資料管理",
      subtitle: "管理您的個人資訊與學籍資料",
      completion: "個人資料完整度",
      completion_description: "建議完善個人資料以便更好地使用系統功能",
      tabs: {
        overview: "總覽",
        basic: "基本資料",
        bank: "銀行帳戶",
        advisor: "指導教授",
      },
      history: "異動紀錄",
      basic_info: "基本資料",
      contact_info: "聯絡資訊",
      bank_info: "銀行帳戶",
      advisor_info: "指導教授",
      completed: "已完成",
      incomplete: "未完成",
      not_set: "未設定",
      student: "學生",
      staff: "職員",

      // Messages and notifications
      loading: "載入中...",
      loading_profile: "正在載入個人資料...",
      profile_may_not_exist: "個人資料可能尚未建立，您可以開始填寫資料",
      connection_error: "連線錯誤",
      connection_error_desc: "無法連接到伺服器，請檢查網路連線",
      load_error: "載入錯誤",
      load_profile_error: "載入個人資料時發生錯誤",
      validation_failed: "驗證失敗",
      validation_failed_desc: "請檢查並修正表單中的錯誤",
      update_success: "成功",
      profile_updated: "個人資料已更新",
      update_failed: "更新失敗",
      update_profile_error: "更新個人資料時發生錯誤",

      // Contact info notice
      contact_notice: "聯絡資訊來自校務系統，如需修改請洽學務處。",

      // Basic info section
      basic_readonly_title: "基本資料 (從 API 取得，無法修改)",
      basic_readonly_notice: "以下資料來自校務系統，如需修改請聯繫相關單位。",
      name: "姓名",
      id_number: "學號/員工編號",
      email: "Email",
      user_type: "身份類別",
      status: "狀態",
      dept_code: "系所代碼",
      dept_name: "系所名稱",
      system_role: "系統角色",
      student_records: "學籍資料",
      degree: "學位",
      enrollment_status: "學籍狀態",
      enrollment_year: "入學年度",
      semester_count: "在學期數",

      // Bank info section
      bank_account_info: "銀行帳戶資訊",
      bank_code: "銀行代碼",
      bank_code_placeholder: "例：808",
      account_number: "帳戶號碼",
      account_number_placeholder: "請輸入完整帳戶號碼",
      bank_document: "銀行帳戶證明文件",
      document_uploaded: "已上傳證明文件",
      document_preview_notice: "點擊預覽按鈕查看已上傳的文件",
      preview: "預覽",
      delete: "刪除",
      uploading: "上傳中...",
      upload_bank_document: "上傳銀行帳戶證明文件",
      file_formats: "• 接受格式：JPG, JPEG, PNG, WebP, PDF",
      file_size_limit: "• 檔案大小限制：10MB",
      upload_suggestion: "• 建議上傳清晰的銀行存摺封面或銀行開戶證明文件",
      saving: "儲存中...",
      save_bank_info: "儲存銀行帳戶資訊",
      select_file: "請選擇文件",
      select_file_desc: "請先選擇要上傳的銀行帳戶證明文件",
      file_too_large: "檔案太大",
      file_size_error: "檔案大小不能超過 10MB",
      document_uploaded_success: "銀行帳戶證明文件已上傳",
      upload_failed: "上傳失敗",
      upload_error: "上傳檔案時發生錯誤",
      document_deleted: "銀行帳戶證明文件已刪除",
      delete_failed: "刪除失敗",
      delete_error: "刪除檔案時發生錯誤",

      // Advisor info section
      advisor_name: "指導教授 姓名",
      advisor_name_placeholder: "例：王小明",
      advisor_email: "指導教授 Email",
      advisor_id: "指導教授 學校工號",
      advisor_id_placeholder: "例：professor123",
      save_advisor_info: "儲存指導教授資訊",

      // History modal
      profile_history: "個人資料異動紀錄",
      old_value: "舊值",
      new_value: "新值",
      reason: "原因",
      no_history: "尚無異動紀錄",
      load_history_error: "載入異動紀錄時發生錯誤",
    },

    // 角色
    roles: {
      student: "學生",
      professor: "教授",
      reviewer: "審核者",
      admin: "管理員",
      sysadmin: "系統管理員",
    },

    // 狀態
    status: {
      draft: "草稿",
      submitted: "已提交",
      under_review: "審核中",
      pending_review: "待審核",
      approved: "已核准",
      rejected: "已駁回",
      pending_recommendation: "待推薦",
      recommended: "已推薦",
    },

    // 表單
    form: {
      submit: "提交申請",
      save_draft: "儲存草稿",
      edit: "編輯",
      view: "查看",
      delete: "刪除",
      approve: "核准",
      reject: "駁回",
      withdraw: "撤回",
      required: "必填",
      optional: "選填",
    },

    // 學生入口網站
    portal: {
      my_applications: "我的申請",
      new_application: "新增申請",
      application_records: "申請記錄",
      no_applications: "尚無申請記錄",
      click_new_application: "點擊「新增申請」開始申請獎學金",
      eligibility: "申請資格",
      form_completion: "表單完成度",
      review_progress: "審核進度",
    },

    // 學生資料欄位
    student: {
      std_stdno: "學號代碼",
      std_stdcode: "學號",
      std_pid: "身份證字號",
      std_cname: "中文姓名",
      std_ename: "英文姓名",
      std_degree: "攻讀學位",
      std_studingstatus: "在學狀態",
      std_nation1: "國籍",
      std_nation2: "其他國籍",
      com_cellphone: "連絡電話",
      com_email: "聯絡信箱",
      com_commadd: "通訊地址",
      bank_account: "匯款帳號",
      trm_year: "學年度",
      trm_term: "學期別",
      trm_ascore_gpa: "學期GPA",
      trm_termcount: "修習學期數",
      trm_placingsrate: "班排名百分比",
      trm_depplacingrate: "系排名百分比",
    },

    // 國籍
    nationalities: {
      TWN: "中華民國",
      USA: "美國",
      JPN: "日本",
      KOR: "韓國",
      CHN: "中國大陸",
      SGP: "新加坡",
      MYS: "馬來西亞",
      THA: "泰國",
      VNM: "越南",
      IDN: "印尼",
      PHL: "菲律賓",
      IND: "印度",
      GBR: "英國",
      FRA: "法國",
      DEU: "德國",
      CAN: "加拿大",
      AUS: "澳洲",
      OTHER: "其他",
    },

    eligibility_tags: {
      // Basic eligibility
      "博士生": "博士生",
      "碩士生": "碩士生",
      "學士生": "學士生",
      "學士班新生": "學士班新生",
      "在學生": "在學生",
      "非在職生": "非在職生",
      "非陸生": "非陸生",
      "中華民國國籍": "中華民國國籍",
      "三年級以下": "三年級以下",
      "一般生": "一般生",
      "逕博生": "逕讀博士生",
      "第一學年": "第一學年"
    },
    rule_types: {
      "nstc": "國科會",
      "moe_1w": "教育部(1萬)",
      "moe_2w": "教育部(2萬)"
    },
    scholarship_sections: {
      "eligible_programs": "可申請項目",
      "eligibility": "申請資格",
      "period": "申請期間",
      "fields": "申請欄位",
      "required_docs": "必要文件",
      "optional_docs": "選填文件"
    },

    // 申請相關
    applications: {
      "submitted_at": "提交時間",
      "withdraw": "撤回",
      "submit": "提交",
      "new_application": "新增申請",
      "edit_application": "編輯申請",
      "save_draft": "儲存草稿",
      "update_draft": "更新草稿",
      "update_application": "更新申請",
      "cancel_edit": "取消編輯",
      "view_details": "查看詳情",
      "delete_draft": "刪除草稿",
      "application_id": "申請編號",
      "application_type": "獎學金類型",
      "application_amount": "申請金額",
      "form_progress": "完成進度",
      "terms_agreement": "條款同意",
      "select_scholarship": "選擇獎學金類型",
      "application_items": "申請項目",
      "single_selection": "單選模式",
      "multiple_selection": "可選擇多個項目",
      "hierarchical_selection": "階層式選擇",
      "select_previous_first": "請先選擇前面的項目",
      "select_one_item": "請選擇一個項目",
      "sequential_selection": "請依序選擇項目（需按順序選取）",
      "select_at_least_one": "請至少選擇一個申請項目",
      "complete_required_fields": "請完成所有必填項目",
      "terms_must_agree": "您必須同意申請條款才能提交申請",
      "cannot_change_type": "編輯模式下無法更改獎學金類型",
      "editing_application_id": "正在編輯申請編號",
      "submitting": "提交中...",
      "updating": "更新中...",
      "saving": "儲存中...",
      "loading": "載入中...",
      "retry": "重試",
      "load_error": "載入錯誤"
    },

    // 通用訊息
    messages: {
      "no_eligible_scholarships": "目前沒有符合資格的獎學金",
      "no_eligible_scholarships_desc": "很抱歉，您目前沒有符合申請資格的獎學金。請稍後再試或聯繫獎學金辦公室。",
      "eligible": "可申請",
      "not_eligible": "不符合申請資格",
      "loading_data": "正在載入資料...",
      "loading_scholarship_info": "載入獎學金資訊...",
      "application_success": "申請提交成功！",
      "draft_saved": "草稿已保存，您可以繼續編輯",
      "draft_updated": "草稿已更新",
      "draft_deleted": "草稿已成功刪除",
      "confirm_delete_draft": "確定要刪除此草稿嗎？此操作無法復原。",
      "delete_error": "刪除草稿時發生錯誤"
    }
  },

  en: {
    // System Title
    system: {
      title: "Scholarship Application and Approval Management System",
      subtitle: "獎學金申請與簽核作業管理系統",
      name: "SAMS",
    },

    // Navigation
    nav: {
      dashboard: "Dashboard",
      applications: "Applications",
      review: "Review",
      admin: "Administration",
      profile: "Profile",
      logout: "Logout",
    },

    // Profile Management
    profile_management: {
      title: "Personal Profile Management",
      subtitle: "Manage your personal information and academic records",
      completion: "Profile Completion",
      completion_description: "We recommend completing your profile for better system functionality",
      tabs: {
        overview: "Overview",
        basic: "Basic Info",
        bank: "Bank Account",
        advisor: "Advisor",
      },
      history: "Change History",
      basic_info: "Basic Information",
      contact_info: "Contact Information",
      bank_info: "Bank Account",
      advisor_info: "Advisor Information",
      completed: "Completed",
      incomplete: "Incomplete",
      not_set: "Not Set",
      student: "Student",
      staff: "Staff",

      // Messages and notifications
      loading: "Loading...",
      loading_profile: "Loading profile...",
      profile_may_not_exist: "Profile may not exist yet, you can start filling in the information",
      connection_error: "Connection Error",
      connection_error_desc: "Unable to connect to server, please check network connection",
      load_error: "Load Error",
      load_profile_error: "Error occurred while loading profile",
      validation_failed: "Validation Failed",
      validation_failed_desc: "Please check and correct errors in the form",
      update_success: "Success",
      profile_updated: "Profile has been updated",
      update_failed: "Update Failed",
      update_profile_error: "Error occurred while updating profile",

      // Contact info notice
      contact_notice: "Contact information is from the academic system. Please contact the Student Affairs Office to modify.",

      // Basic info section
      basic_readonly_title: "Basic Information (From API, Read Only)",
      basic_readonly_notice: "The following information is from the academic system. Please contact relevant departments to modify.",
      name: "Name",
      id_number: "Student ID/Employee ID",
      email: "Email",
      user_type: "User Type",
      status: "Status",
      dept_code: "Department Code",
      dept_name: "Department Name",
      system_role: "System Role",
      student_records: "Academic Records",
      degree: "Degree",
      enrollment_status: "Enrollment Status",
      enrollment_year: "Enrollment Year",
      semester_count: "Semesters Completed",

      // Bank info section
      bank_account_info: "Bank Account Information",
      bank_code: "Bank Code",
      bank_code_placeholder: "e.g., 808",
      account_number: "Account Number",
      account_number_placeholder: "Enter complete account number",
      bank_document: "Bank Account Proof Document",
      document_uploaded: "Document Uploaded",
      document_preview_notice: "Click preview button to view uploaded document",
      preview: "Preview",
      delete: "Delete",
      uploading: "Uploading...",
      upload_bank_document: "Upload Bank Account Proof Document",
      file_formats: "• Accepted formats: JPG, JPEG, PNG, WebP, PDF",
      file_size_limit: "• File size limit: 10MB",
      upload_suggestion: "• We recommend uploading a clear bank passbook cover or account opening certificate",
      saving: "Saving...",
      save_bank_info: "Save Bank Account Information",
      select_file: "Please Select File",
      select_file_desc: "Please select a bank account proof document to upload first",
      file_too_large: "File Too Large",
      file_size_error: "File size cannot exceed 10MB",
      document_uploaded_success: "Bank account proof document has been uploaded",
      upload_failed: "Upload Failed",
      upload_error: "Error occurred while uploading file",
      document_deleted: "Bank account proof document has been deleted",
      delete_failed: "Delete Failed",
      delete_error: "Error occurred while deleting file",

      // Advisor info section
      advisor_name: "Advisor Name",
      advisor_name_placeholder: "e.g., John Smith",
      advisor_email: "Advisor Email",
      advisor_id: "Advisor School ID",
      advisor_id_placeholder: "e.g., professor123",
      save_advisor_info: "Save Advisor Information",

      // History modal
      profile_history: "Profile Change History",
      old_value: "Old Value",
      new_value: "New Value",
      reason: "Reason",
      no_history: "No change history yet",
      load_history_error: "Error occurred while loading change history",
    },

    // Roles
    roles: {
      student: "Student",
      professor: "Professor",
      reviewer: "Reviewer",
      admin: "Administrator",
      sysadmin: "System Administrator",
    },

    // Status
    status: {
      draft: "Draft",
      submitted: "Submitted",
      under_review: "Under Review",
      pending_review: "Pending Review",
      approved: "Approved",
      rejected: "Rejected",
      pending_recommendation: "Pending Recommendation",
      recommended: "Recommended",
    },

    // Form
    form: {
      submit: "Submit Application",
      save_draft: "Save Draft",
      edit: "Edit",
      view: "View",
      delete: "Delete",
      approve: "Approve",
      reject: "Reject",
      withdraw: "Withdraw",
      required: "Required",
      optional: "Optional",
    },

    // Student Portal
    portal: {
      my_applications: "My Applications",
      new_application: "New Application",
      application_records: "Application Records",
      no_applications: "No application records yet",
      click_new_application: "Click 'New Application' to start applying for scholarship",
      eligibility: "Eligibility",
      form_completion: "Form Completion",
      review_progress: "Review Progress",
    },

    // Student Fields
    student: {
      std_stdno: "Student ID Code",
      std_stdcode: "Student ID",
      std_pid: "National ID",
      std_cname: "Chinese Name",
      std_ename: "English Name",
      std_degree: "Degree Program",
      std_studingstatus: "Enrollment Status",
      std_nation1: "Nationality",
      std_nation2: "Other Nationality",
      com_cellphone: "Phone Number",
      com_email: "Email Address",
      com_commadd: "Mailing Address",
      bank_account: "Bank Account",
      trm_year: "Academic Year",
      trm_term: "Semester",
      trm_ascore_gpa: "Semester GPA",
      trm_termcount: "Semesters Completed",
      trm_placingsrate: "Class Ranking %",
      trm_depplacingrate: "Department Ranking %",
    },

    // Nationalities
    nationalities: {
      TWN: "Taiwan (ROC)",
      USA: "United States",
      JPN: "Japan",
      KOR: "South Korea",
      CHN: "China (PRC)",
      SGP: "Singapore",
      MYS: "Malaysia",
      THA: "Thailand",
      VNM: "Vietnam",
      IDN: "Indonesia",
      PHL: "Philippines",
      IND: "India",
      GBR: "United Kingdom",
      FRA: "France",
      DEU: "Germany",
      CAN: "Canada",
      AUS: "Australia",
      OTHER: "Other",
    },

    eligibility_tags: {
      // Basic eligibility
      "碩士生": "Master Student",
      "學士生": "Undergraduate Student",
      "學士班新生": "Undergraduate Freshman",
      "博士生": "PhD Student",
      "在學生": "Current Student",
      "非在職生": "Full-time Student",
      "非陸生": "Non-Mainland Student",
      "中華民國國籍": "ROC Nationality",
      "三年級以下": "Below 3rd Year",
      "一般生": "Regular Student",
      "逕博生": "Direct PhD Student",
      "第一學年": "First Academic Year"
    },
    rule_types: {
      "nstc": "NSTC",
      "moe_1w": "MOE (10K)",
      "moe_2w": "MOE (20K)"
    },
    scholarship_sections: {
      "eligible_programs": "Eligible Programs",
      "eligibility": "Eligibility",
      "period": "Application Period",
      "fields": "Required Fields",
      "required_docs": "Required Documents",
      "optional_docs": "Optional Documents"
    },

    // Application related
    applications: {
      "submitted_at": "Submitted At",
      "withdraw": "Withdraw",
      "submit": "Submit",
      "new_application": "New Application",
      "edit_application": "Edit Application",
      "save_draft": "Save Draft",
      "update_draft": "Update Draft",
      "update_application": "Update Application",
      "cancel_edit": "Cancel Edit",
      "view_details": "View Details",
      "delete_draft": "Delete Draft",
      "application_id": "Application ID",
      "application_type": "Scholarship Type",
      "application_amount": "Application Amount",
      "form_progress": "Progress",
      "terms_agreement": "Terms Agreement",
      "select_scholarship": "Select scholarship type",
      "application_items": "Application Items",
      "single_selection": "Single selection",
      "multiple_selection": "Multiple selections allowed",
      "hierarchical_selection": "Hierarchical selection",
      "select_previous_first": "Select previous items first",
      "select_one_item": "Please select one item",
      "sequential_selection": "Please select items in order (sequential selection required)",
      "select_at_least_one": "Please select at least one item",
      "complete_required_fields": "Please complete all required fields",
      "terms_must_agree": "You must agree to the terms and conditions to submit the application",
      "cannot_change_type": "Cannot change scholarship type in edit mode",
      "editing_application_id": "Editing Application ID",
      "submitting": "Submitting...",
      "updating": "Updating...",
      "saving": "Saving...",
      "loading": "Loading...",
      "retry": "Retry",
      "load_error": "Load Error"
    },

    // General messages
    messages: {
      "no_eligible_scholarships": "No Eligible Scholarships",
      "no_eligible_scholarships_desc": "Sorry, you are not currently eligible for any scholarships. Please try again later or contact the scholarship office.",
      "eligible": "Eligible",
      "not_eligible": "Not Eligible",
      "loading_data": "Loading data...",
      "loading_scholarship_info": "Loading scholarship information...",
      "application_success": "Application submitted successfully!",
      "draft_saved": "Draft saved successfully. You can continue editing.",
      "draft_updated": "Draft updated",
      "draft_deleted": "Draft deleted successfully",
      "confirm_delete_draft": "Are you sure you want to delete this draft? This action cannot be undone.",
      "delete_error": "Error occurred while deleting draft"
    }
  },
}

export function getTranslation(locale: 'zh' | 'en', key: string): string {
  const keys = key.split('.')
  let value: any = translations[locale]

  for (const k of keys) {
    value = value?.[k]
  }

  return value || key
}
