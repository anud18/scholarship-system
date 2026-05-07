export type Locale = "zh" | "en";

export const defaultLocale: Locale = "zh";

export const locales: Locale[] = ["zh", "en"];

export const translations = {
  zh: {
    // 系統標題
    system: {
      title: "獎學金申請與簽核系統",
      subtitle: "NYCU Admissions Scholarship System",
      name: "NYCU Admissions Scholarship System",
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
      id_number: "學號",
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
      bank_code_placeholder: "例：700",
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
      advisor_id: "指導教授 本校人事編號",
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

    // Session 管理
    session: {
      expired_title: "登入已過期",
      expired_message: "您的登入已過期，請重新登入以繼續使用系統。",
      unauthorized_title: "權限不足",
      unauthorized_message:
        "您沒有權限執行此操作，請聯繫管理員或重新登入。",
      forbidden_title: "存取被拒絕",
      forbidden_message: "您無法存取此資源，請確認您的權限或重新登入。",
      relogin_button: "重新登入",
    },

    // 狀態
    status: {
      draft: "草稿",
      submitted: "已提交",
      under_review: "審核中",
      pending_review: "待審核",
      approved: "已核准",
      rejected: "已駁回",
      returned: "已退回",
      withdrawn: "已撤回",
      cancelled: "已取消",
      deleted: "已刪除",
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
      click_new_application_hint: "您可以點擊「新增申請」開始申請獎學金",
      eligibility: "申請資格",
      form_completion: "表單完成度",
      review_progress: "審核進度",
      applications_subtitle: "查看您的獎學金申請狀態與進度",
      fetch_scholarships_error: "無法獲取獎學金資料",
      fetch_application_info_error: "無法獲取申請資訊",
      fetch_application_info_exception: "獲取申請資訊時發生錯誤",
      document_request: {
        marked_complete: "文件補件已標記為完成",
        operation_failed: "操作失敗",
        mark_complete_error: "標記完成時發生錯誤",
      },
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
      博士生: "博士生",
      碩士生: "碩士生",
      學士生: "學士生",
      學士班新生: "學士班新生",
      在學生: "在學生",
      非在職生: "非在職生",
      非陸生: "非陸生",
      中華民國國籍: "中華民國國籍",
      三年級以下: "三年級以下",
      一般生: "一般生",
      逕博生: "逕讀博士生",
      第一學年: "第一學年",
    },
    rule_types: {
      nstc: "國科會博士生獎學金",
      moe_1w: "教育部博士生獎學金 (指導教授配合款一萬)",
      moe_2w: "教育部博士生獎學金 (指導教授配合款兩萬)",
    },
    scholarship_sections: {
      eligible_programs: "可申請項目",
      eligibility: "申請資格",
      period: "申請期間",
      fields: "申請欄位",
      required_docs: "必要文件",
      optional_docs: "選填文件",
    },

    // 申請相關
    applications: {
      submitted_at: "提交時間",
      withdraw: "撤回",
      submit: "提交",
      new_application: "新增申請",
      edit_application: "編輯申請",
      save_draft: "儲存草稿",
      update_draft: "更新草稿",
      update_application: "更新申請",
      cancel_edit: "取消編輯",
      view_details: "查看詳情",
      delete_draft: "刪除草稿",
      application_id: "申請編號",
      application_type: "獎學金類型",
      application_amount: "申請金額",
      form_progress: "完成進度",
      terms_agreement: "條款同意",
      select_scholarship: "選擇獎學金類型",
      application_items: "申請項目",
      single_selection: "單選模式",
      multiple_selection: "可選擇多個項目",
      hierarchical_selection: "階層式選擇",
      select_previous_first: "請先選擇前面的項目",
      select_one_item: "請選擇一個項目",
      sequential_selection: "請依序選擇項目（需按順序選取）",
      select_at_least_one: "請至少選擇一個申請項目",
      complete_required_fields: "請完成所有必填項目",
      terms_must_agree: "您必須同意申請條款才能提交申請",
      cannot_change_type: "編輯模式下無法更改獎學金類型",
      editing_application_id: "正在編輯申請編號",
      submitting: "提交中...",
      updating: "更新中...",
      saving: "儲存中...",
      loading: "載入中...",
      retry: "重試",
      load_error: "載入錯誤",
      please_select_scholarship: "請選擇獎學金類型",
      submit_failed: "提交失敗",
      application_info: "申請資訊",
      missing: "不符",
      not_eligible_short: "不符資格",
      not_eligible_parenthetical: "（不符資格）",
      warnings: "注意事項",
    },

    // 批次匯入
    batch_import: {
      field_labels: {
        student_id: "學號",
        student_name: "姓名",
        postal_account: "郵局帳號",
        advisor_name: "指導教授姓名",
        advisor_email: "指導教授Email",
        advisor_nycu_id: "指導教授本校人事編號",
        sub_types: "子類型",
        custom_fields: "其他欄位",
        row_number: "行號",
      },
    },

    // 通用訊息
    messages: {
      no_eligible_scholarships: "目前沒有符合資格的獎學金",
      no_eligible_scholarships_desc:
        "很抱歉，您目前沒有符合申請資格的獎學金。請稍後再試或聯繫獎學金辦公室。",
      eligible: "可申請",
      not_eligible: "不符合申請資格",
      loading_data: "正在載入資料...",
      loading_scholarship_info: "載入獎學金資訊...",
      application_success: "申請提交成功！",
      application_success_with_progress: "申請提交成功！請在「我的申請」查看進度",
      draft_saved: "草稿已保存，您可以繼續編輯",
      draft_updated: "草稿已更新",
      draft_deleted: "草稿已成功刪除",
      draft_save_failed: "儲存草稿失敗",
      save_failed: "保存失敗",
      confirm_delete_draft: "確定要刪除此草稿嗎？此操作無法復原。",
      delete_error: "刪除草稿時發生錯誤",
      unknown_error: "發生未知錯誤",
    },

    // 學生申請精靈
    wizard: {
      mobile_step_label: "步驟",
      sidebar: {
        title: "申請流程",
        subtitle: "請依序完成以下步驟",
        overall_progress: "整體進度",
      },
      steps: {
        notice: {
          label: "注意事項與同意",
          description: "閱讀並同意申請須知",
        },
        review: {
          label: "確認學籍資料",
          description: "檢視學校資料庫資料",
        },
        apply: {
          label: "填寫資料與申請獎學金",
          description: "填寫個人資料並申請獎學金",
        },
      },
    },

    // 檔案上傳元件
    form_upload: {
      drag_drop: "拖放檔案到此處或點擊上傳",
      supported_formats: "支援格式",
      max_file_size: "最大檔案大小",
      choose_file: "選擇檔案",
      uploaded_files: "已上傳檔案",
      uploaded: "已上傳",
      exists: "已存在",
      complete: "完成",
      failed: "失敗",
      files_suffix: "個檔案",
      bankbook_cover: "存摺封面",
      replace_existing_notice: "您可以上傳新檔案來替換現有檔案",
      accepted_formats_label: "接受格式：",
      file_size_limit_label: "檔案大小限制：",
      max_files_label: "最多檔案數：",
      preview_open_failed: "無法開啟預覽，請稍後再試",
      view_sample_document: "查看範例文件",
      loading_form: "載入表單中...",
      form_config_not_set: "尚未設定表單配置",
      application_information: "申請資訊",
      please_complete_required_info: "請填寫所有必要資訊",
      required_documents: "必要文件",
      please_upload_required_docs: "請上傳所有必要文件",
      no_requirements_configured: "此獎學金類型尚未設定申請要求",
      load_form_config_failed: "無法載入表單配置",
      load_form_config_error: "載入表單配置時發生錯誤",
    },

    // 申請文件上傳對話框
    form_dialog: {
      upload_success_prefix: "成功上傳",
      upload_success_suffix: "個檔案",
      partial_upload_failed: "部分檔案上傳失敗",
      upload_failed: "上傳失敗",
      upload_application_documents: "上傳申請文件",
      application_id: "申請 ID",
      document_type: "文件類型",
      select_document_type: "選擇文件類型",
      no_document_requirements: "此獎學金類型尚未設定文件需求，請聯繫管理員",
      uploading: "上傳中...",
      cancel: "取消",
      upload: "上傳",
    },

    // 對話框
    dialogs: {
      preview: {
        title: "文件預覽",
        loading: "載入中...",
        cannot_preview: "此文件類型無法預覽",
        open_in_new_window: "在新視窗開啟",
        download: "下載",
        close: "關閉",
      },
      delete_application: {
        reason_required: "請輸入刪除原因",
        delete_success: "申請已成功刪除",
        delete_failed: "刪除失敗",
        delete_error: "刪除申請時發生錯誤",
        confirm_title: "確認刪除申請",
        confirm_description: "此操作將永久移除申請資料，且無法撤銷。",
        application_label: "申請：",
        cascade_notice:
          "刪除後相關審查、造冊明細等關聯資料也會一併移除，但操作紀錄會永久保留。",
        reason_label: "刪除原因",
        reason_placeholder: "請輸入刪除原因...",
        reason_recorded_notice: "刪除原因將記錄在操作紀錄中",
        cancel: "取消",
        deleting: "刪除中...",
        confirm_delete: "確認刪除",
      },
      application_detail: {
        title: "申請詳情",
        application_id: "申請編號",
        basic_info: "基本資訊",
        applicant: "申請者",
        student_id: "學號",
        academy: "學院",
        department: "系所",
        degree: "學位",
        terms_enrolled: "就讀學期數",
        scholarship_type: "獎學金類型",
        status: "申請狀態",
        created_at: "建立時間",
        submitted_at: "提交時間",
        review_progress: "審核進度",
        application_fields: "申請欄位",
        loading_failed: "載入失敗",
        loading_fields: "載入申請欄位中...",
        application_form_fields: "申請表單欄位",
        personal_statement: "個人陳述",
        uploaded_files: "已上傳文件",
        loading_files: "載入文件中...",
        fixed_document: "固定文件",
        no_files: "尚未上傳任何文件",
        // Bank verification
        bank_verification_completed: "銀行帳戶驗證已完成",
        bank_verification_unable: "無法完成銀行帳戶驗證",
        bank_verification_error: "銀行帳戶驗證過程中發生錯誤",
        bank_verified: "已驗證",
        bank_verification_failed: "驗證失敗",
        bank_verification_pending: "驗證中",
        bank_not_verified: "未驗證",
        bank_verified_desc: "銀行帳戶已通過驗證",
        bank_verification_failed_desc: "銀行帳戶驗證失敗",
        bank_verification_pending_desc: "銀行帳戶驗證進行中",
        bank_not_verified_desc: "銀行帳戶尚未驗證",
        verifying: "驗證中...",
        start_verification: "開始驗證",
        verification_details: "驗證詳情",
        verified_at: "驗證時間",
        account_holder: "帳戶持有人",
        confidence_score: "信心分數",
        verification_failure_reason: "驗證失敗原因",
        // Form config errors
        scholarship_type_fetch_failed: "無法獲取獎學金類型信息",
        scholarship_type_fetch_error: "獲取獎學金類型時發生錯誤",
        scholarship_type_undetermined: "無法確定獎學金類型",
        form_config_load_failed: "無法載入表單配置",
        form_config_load_error: "載入表單配置時發生錯誤",
      },
    },
  },

  en: {
    // System Title
    system: {
      title: "NYCU Admissions Scholarship System",
      subtitle: "獎學金申請與簽核系統",
      name: "NYCU Admissions Scholarship System",
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
      completion_description:
        "We recommend completing your profile for better system functionality",
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
      profile_may_not_exist:
        "Profile may not exist yet, you can start filling in the information",
      connection_error: "Connection Error",
      connection_error_desc:
        "Unable to connect to server, please check network connection",
      load_error: "Load Error",
      load_profile_error: "Error occurred while loading profile",
      validation_failed: "Validation Failed",
      validation_failed_desc: "Please check and correct errors in the form",
      update_success: "Success",
      profile_updated: "Profile has been updated",
      update_failed: "Update Failed",
      update_profile_error: "Error occurred while updating profile",

      // Contact info notice
      contact_notice:
        "Contact information is from the academic system. Please contact the Student Affairs Office to modify.",

      // Basic info section
      basic_readonly_title: "Basic Information (From API, Read Only)",
      basic_readonly_notice:
        "The following information is from the academic system. Please contact relevant departments to modify.",
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
      upload_suggestion:
        "• We recommend uploading a clear bank passbook cover or account opening certificate",
      saving: "Saving...",
      save_bank_info: "Save Bank Account Information",
      select_file: "Please Select File",
      select_file_desc:
        "Please select a bank account proof document to upload first",
      file_too_large: "File Too Large",
      file_size_error: "File size cannot exceed 10MB",
      document_uploaded_success:
        "Bank account proof document has been uploaded",
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

    // Session management
    session: {
      expired_title: "Session Expired",
      expired_message:
        "Your session has expired. Please log in again to continue.",
      unauthorized_title: "Unauthorized",
      unauthorized_message:
        "You don't have permission for this action. Please contact admin or log in again.",
      forbidden_title: "Access Denied",
      forbidden_message:
        "You cannot access this resource. Please check your permissions or log in again.",
      relogin_button: "Log In Again",
    },

    // Status
    status: {
      draft: "Draft",
      submitted: "Submitted",
      under_review: "Under Review",
      pending_review: "Pending Review",
      approved: "Approved",
      rejected: "Rejected",
      returned: "Returned",
      withdrawn: "Withdrawn",
      cancelled: "Cancelled",
      deleted: "Deleted",
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
      click_new_application:
        "Click 'New Application' to start applying for scholarship",
      click_new_application_hint:
        "Click 'New Application' to start applying for scholarship",
      eligibility: "Eligibility",
      form_completion: "Form Completion",
      review_progress: "Review Progress",
      applications_subtitle:
        "View your scholarship application status and progress",
      fetch_scholarships_error: "Unable to fetch scholarship data",
      fetch_application_info_error: "Unable to fetch application info",
      fetch_application_info_exception:
        "Error occurred while fetching application info",
      document_request: {
        marked_complete: "Document supplement marked as complete",
        operation_failed: "Operation failed",
        mark_complete_error: "Error occurred while marking as complete",
      },
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
      碩士生: "Master Student",
      學士生: "Undergraduate Student",
      學士班新生: "Undergraduate Freshman",
      博士生: "PhD Student",
      在學生: "Current Student",
      非在職生: "Full-time Student",
      非陸生: "Non-Mainland Student",
      中華民國國籍: "ROC Nationality",
      三年級以下: "Below 3rd Year",
      一般生: "Regular Student",
      逕博生: "Direct PhD Student",
      第一學年: "First Academic Year",
    },
    rule_types: {
      nstc: "NSTC PhD Scholarship",
      moe_1w: "MOE PhD Scholarship (Advisor Matching Fund - 10K)",
      moe_2w: "MOE PhD Scholarship (Advisor Matching Fund - 20K)",
    },
    scholarship_sections: {
      eligible_programs: "Eligible Programs",
      eligibility: "Eligibility",
      period: "Application Period",
      fields: "Required Fields",
      required_docs: "Required Documents",
      optional_docs: "Optional Documents",
    },

    // Application related
    applications: {
      submitted_at: "Submitted At",
      withdraw: "Withdraw",
      submit: "Submit",
      new_application: "New Application",
      edit_application: "Edit Application",
      save_draft: "Save Draft",
      update_draft: "Update Draft",
      update_application: "Update Application",
      cancel_edit: "Cancel Edit",
      view_details: "View Details",
      delete_draft: "Delete Draft",
      application_id: "Application ID",
      application_type: "Scholarship Type",
      application_amount: "Application Amount",
      form_progress: "Progress",
      terms_agreement: "Terms Agreement",
      select_scholarship: "Select scholarship type",
      application_items: "Application Items",
      single_selection: "Single selection",
      multiple_selection: "Multiple selections allowed",
      hierarchical_selection: "Hierarchical selection",
      select_previous_first: "Select previous items first",
      select_one_item: "Please select one item",
      sequential_selection:
        "Please select items in order (sequential selection required)",
      select_at_least_one: "Please select at least one item",
      complete_required_fields: "Please complete all required fields",
      terms_must_agree:
        "You must agree to the terms and conditions to submit the application",
      cannot_change_type: "Cannot change scholarship type in edit mode",
      editing_application_id: "Editing Application ID",
      submitting: "Submitting...",
      updating: "Updating...",
      saving: "Saving...",
      loading: "Loading...",
      retry: "Retry",
      load_error: "Load Error",
      please_select_scholarship: "Please select scholarship type",
      submit_failed: "Submission failed",
      application_info: "Application Info",
      missing: "Missing",
      not_eligible_short: "Not eligible",
      not_eligible_parenthetical: "(Not eligible)",
      warnings: "Warnings",
    },

    // Batch Import
    batch_import: {
      field_labels: {
        student_id: "Student ID",
        student_name: "Name",
        postal_account: "Postal Account",
        advisor_name: "Advisor Name",
        advisor_email: "Advisor Email",
        advisor_nycu_id: "Advisor NYCU ID",
        sub_types: "Sub Types",
        custom_fields: "Custom Fields",
        row_number: "Row Number",
      },
    },

    // General messages
    messages: {
      no_eligible_scholarships: "No Eligible Scholarships",
      no_eligible_scholarships_desc:
        "Sorry, you are not currently eligible for any scholarships. Please try again later or contact the scholarship office.",
      eligible: "Eligible",
      not_eligible: "Not Eligible",
      loading_data: "Loading data...",
      loading_scholarship_info: "Loading scholarship information...",
      application_success: "Application submitted successfully!",
      application_success_with_progress:
        "Application submitted successfully! View status under 'My Applications'",
      draft_saved: "Draft saved successfully. You can continue editing.",
      draft_updated: "Draft updated",
      draft_deleted: "Draft deleted successfully",
      draft_save_failed: "Failed to save draft",
      save_failed: "Save failed",
      confirm_delete_draft:
        "Are you sure you want to delete this draft? This action cannot be undone.",
      delete_error: "Error occurred while deleting draft",
      unknown_error: "An unknown error occurred",
    },

    // Student Application Wizard
    wizard: {
      mobile_step_label: "Step",
      sidebar: {
        title: "Application Steps",
        subtitle: "Complete the following steps in order",
        overall_progress: "Overall Progress",
      },
      steps: {
        notice: {
          label: "Notice & Agreement",
          description: "Read and agree to application notice",
        },
        review: {
          label: "Confirm Student Records",
          description: "Review school database records",
        },
        apply: {
          label: "Apply for Scholarship",
          description: "Fill out personal information and apply for scholarship",
        },
      },
    },

    // File Upload Component
    form_upload: {
      drag_drop: "Drag and drop files here or click to upload",
      supported_formats: "Supported formats",
      max_file_size: "Maximum file size",
      choose_file: "Choose File",
      uploaded_files: "Uploaded Files",
      uploaded: "Uploaded",
      exists: "Exists",
      complete: "Complete",
      failed: "Failed",
      files_suffix: "files",
      bankbook_cover: "Bankbook Cover",
      replace_existing_notice: "You can upload a new file to replace the existing one",
      accepted_formats_label: "Accepted formats:",
      file_size_limit_label: "File size limit:",
      max_files_label: "Maximum number of files:",
      preview_open_failed: "Unable to open preview, please try again later",
      view_sample_document: "View Sample Document",
      loading_form: "Loading form...",
      form_config_not_set: "Form configuration not yet set",
      application_information: "Application Information",
      please_complete_required_info: "Please complete all required information",
      required_documents: "Required Documents",
      please_upload_required_docs: "Please upload all required documents",
      no_requirements_configured:
        "Application requirements not yet configured for this scholarship type",
      load_form_config_failed: "Unable to load form configuration",
      load_form_config_error: "Error occurred while loading form configuration",
    },

    // Application File Upload Dialog
    form_dialog: {
      upload_success_prefix: "Successfully uploaded",
      upload_success_suffix: "file(s)",
      partial_upload_failed: "Some files failed to upload",
      upload_failed: "Upload failed",
      upload_application_documents: "Upload Application Documents",
      application_id: "Application ID",
      document_type: "Document Type",
      select_document_type: "Select document type",
      no_document_requirements:
        "Document requirements not yet configured for this scholarship type; please contact administrator",
      uploading: "Uploading...",
      cancel: "Cancel",
      upload: "Upload",
    },

    // Dialogs
    dialogs: {
      preview: {
        title: "Document Preview",
        loading: "Loading...",
        cannot_preview: "This document type cannot be previewed",
        open_in_new_window: "Open in New Window",
        download: "Download",
        close: "Close",
      },
      delete_application: {
        reason_required: "Please enter a reason for deletion",
        delete_success: "Application successfully deleted",
        delete_failed: "Deletion failed",
        delete_error: "Error occurred while deleting application",
        confirm_title: "Confirm Deletion",
        confirm_description:
          "This action will permanently remove the application and cannot be undone.",
        application_label: "Application:",
        cascade_notice:
          "Related review records, distribution details, and other associated data will also be removed; operation logs are permanently retained.",
        reason_label: "Reason for Deletion",
        reason_placeholder: "Enter reason for deletion...",
        reason_recorded_notice:
          "The reason will be recorded in the operation log",
        cancel: "Cancel",
        deleting: "Deleting...",
        confirm_delete: "Confirm Delete",
      },
      application_detail: {
        title: "Application Details",
        application_id: "Application ID",
        basic_info: "Basic Information",
        applicant: "Applicant",
        student_id: "Student ID",
        academy: "College",
        department: "Department",
        degree: "Degree",
        terms_enrolled: "Semester",
        scholarship_type: "Scholarship Type",
        status: "Application Status",
        created_at: "Created At",
        submitted_at: "Submitted At",
        review_progress: "Review Progress",
        application_fields: "Application Fields",
        loading_failed: "Failed to load",
        loading_fields: "Loading application fields...",
        application_form_fields: "Application Form Fields",
        personal_statement: "Personal Statement",
        uploaded_files: "Uploaded Documents",
        loading_files: "Loading documents...",
        fixed_document: "Standard Documents",
        no_files: "No documents uploaded yet",
        // Bank verification
        bank_verification_completed: "Bank account verification completed",
        bank_verification_unable: "Unable to complete bank account verification",
        bank_verification_error:
          "Error occurred during bank account verification",
        bank_verified: "Verified",
        bank_verification_failed: "Verification Failed",
        bank_verification_pending: "Verifying",
        bank_not_verified: "Not Verified",
        bank_verified_desc: "Bank account has been verified",
        bank_verification_failed_desc: "Bank account verification failed",
        bank_verification_pending_desc:
          "Bank account verification in progress",
        bank_not_verified_desc: "Bank account not yet verified",
        verifying: "Verifying...",
        start_verification: "Start Verification",
        verification_details: "Verification Details",
        verified_at: "Verification Time",
        account_holder: "Account Holder",
        confidence_score: "Confidence Score",
        verification_failure_reason: "Failure Reason",
        // Form config errors
        scholarship_type_fetch_failed: "Unable to fetch scholarship type info",
        scholarship_type_fetch_error:
          "Error occurred while fetching scholarship type",
        scholarship_type_undetermined: "Unable to determine scholarship type",
        form_config_load_failed: "Unable to load form configuration",
        form_config_load_error:
          "Error occurred while loading form configuration",
      },
    },
  },
};

export function getTranslation(locale: "zh" | "en", key: string): string {
  const keys = key.split(".");
  let value: any = translations[locale];

  for (const k of keys) {
    value = value?.[k];
  }

  return value || key;
}
