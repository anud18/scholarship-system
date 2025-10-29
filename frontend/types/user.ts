// 統一的 User 類型定義
export interface User {
  id: string;
  nycu_id: string;
  email: string;
  name: string;
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  user_type?: "student" | "employee";
  status?: "在學" | "畢業" | "在職" | "退休";
  dept_code?: string;
  dept_name?: string;
  college_code?: string;
  college_name?: string;
  comment?: string;
  last_login_at?: string;
  created_at: string;
  updated_at: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
  // 向後相容性欄位
  username?: string;
  full_name?: string;
  is_active?: boolean;
}

// 學生特定的 User 類型
export interface StudentUser extends User {
  role: "student";
  user_type: "student";
  status: "在學" | "畢業";
  studentType?: "phd" | "master" | "undergraduate" | "other";
}

// 教職員特定的 User 類型
export interface EmployeeUser extends User {
  role: "professor" | "college" | "admin" | "super_admin";
  user_type: "employee";
  status: "在職" | "退休";
}
