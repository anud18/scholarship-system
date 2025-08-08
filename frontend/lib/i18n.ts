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
