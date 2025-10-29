import { getTranslation } from "@/lib/i18n";

export interface ValidationRule {
  required?: boolean;
  min?: number;
  max?: number;
  pattern?: RegExp;
  custom?: (value: any) => boolean;
}

export interface ValidationResult {
  isValid: boolean;
  error?: string;
  warning?: string;
  info?: string;
}

export class FormValidator {
  private locale: "zh" | "en";

  constructor(locale: "zh" | "en" = "zh") {
    this.locale = locale;
  }

  private t(key: string): string {
    return getTranslation(this.locale, key);
  }

  validateGPA(value: string, studentType: string): ValidationResult {
    const gpa = Number.parseFloat(value);

    if (!value) {
      return {
        isValid: false,
        error: this.locale === "zh" ? "請輸入GPA" : "Please enter GPA",
      };
    }

    if (isNaN(gpa) || gpa < 0 || gpa > 4) {
      return {
        isValid: false,
        error:
          this.locale === "zh" ? "GPA必須在0-4之間" : "GPA must be between 0-4",
      };
    }

    if (studentType === "undergraduate" && gpa < 3.38) {
      return {
        isValid: true,
        warning:
          this.locale === "zh"
            ? "GPA低於標準3.38，建議提供排名證明"
            : "GPA below 3.38 standard, ranking proof recommended",
      };
    }

    if (gpa >= 3.8) {
      return {
        isValid: true,
        info:
          this.locale === "zh"
            ? "優秀的學業表現！"
            : "Excellent academic performance!",
      };
    }

    return { isValid: true };
  }

  validateRanking(value: string, studentType: string): ValidationResult {
    const ranking = Number.parseFloat(value);

    if (!value) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "請輸入排名百分比"
            : "Please enter ranking percentage",
      };
    }

    if (isNaN(ranking) || ranking < 0 || ranking > 100) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "排名百分比必須在0-100之間"
            : "Ranking percentage must be between 0-100",
      };
    }

    if (studentType === "undergraduate" && ranking > 35) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "排名需在前35%以內"
            : "Ranking must be within top 35%",
      };
    }

    if (ranking <= 10) {
      return {
        isValid: true,
        info:
          this.locale === "zh"
            ? "前10%排名，符合優秀學生標準"
            : "Top 10% ranking, meets excellent student criteria",
      };
    }

    return { isValid: true };
  }

  validateTermCount(value: string, studentType: string): ValidationResult {
    const termCount = Number.parseInt(value);

    if (!value) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "請輸入修習學期數"
            : "Please enter semesters completed",
      };
    }

    if (isNaN(termCount) || termCount < 1) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "修習學期數必須大於0"
            : "Semesters completed must be greater than 0",
      };
    }

    if (studentType === "undergraduate" && termCount > 6) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "學士班新生獎學金修習學期數不得超過6學期"
            : "Undergraduate scholarship semesters cannot exceed 6",
      };
    }

    if (studentType === "phd" && termCount > 2) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "博士生研究獎學金修習學期數不得超過2學期"
            : "PhD scholarship semesters cannot exceed 2",
      };
    }

    return { isValid: true };
  }

  validatePhone(value: string): ValidationResult {
    if (!value) {
      return {
        isValid: false,
        error:
          this.locale === "zh" ? "請輸入連絡電話" : "Please enter phone number",
      };
    }

    const phonePattern = /^09\d{8}$|^\d{2,3}-\d{6,8}$/;
    if (!phonePattern.test(value)) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "請輸入有效的電話號碼格式"
            : "Please enter a valid phone number format",
      };
    }

    return { isValid: true };
  }

  validateBankAccount(value: string): ValidationResult {
    if (!value) {
      return {
        isValid: false,
        error:
          this.locale === "zh" ? "請輸入銀行帳號" : "Please enter bank account",
      };
    }

    if (value.length < 10 || value.length > 16) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "銀行帳號長度應在10-16位數之間"
            : "Bank account should be 10-16 digits",
      };
    }

    const accountPattern = /^\d+$/;
    if (!accountPattern.test(value)) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "銀行帳號只能包含數字"
            : "Bank account can only contain numbers",
      };
    }

    return { isValid: true };
  }

  validateEmail(value: string): ValidationResult {
    if (!value) {
      return {
        isValid: false,
        error: this.locale === "zh" ? "請輸入電子郵件" : "Please enter email",
      };
    }

    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(value)) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "請輸入有效的電子郵件格式"
            : "Please enter a valid email format",
      };
    }

    return { isValid: true };
  }

  validateAddress(value: string): ValidationResult {
    if (!value) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "請輸入通訊地址"
            : "Please enter mailing address",
      };
    }

    if (value.length < 10) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "地址長度過短，請輸入完整地址"
            : "Address too short, please enter complete address",
      };
    }

    return { isValid: true };
  }

  validateResearchProposal(value: string): ValidationResult {
    if (!value) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "請輸入研究計畫摘要"
            : "Please enter research proposal summary",
      };
    }

    if (value.length < 100) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "研究計畫摘要至少需要100字"
            : "Research proposal summary requires at least 100 characters",
      };
    }

    if (value.length > 2000) {
      return {
        isValid: false,
        error:
          this.locale === "zh"
            ? "研究計畫摘要不得超過2000字"
            : "Research proposal summary cannot exceed 2000 characters",
      };
    }

    return { isValid: true };
  }
}
