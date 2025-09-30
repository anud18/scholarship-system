export type Locale = "zh" | "en"

export class FormValidator {
  constructor(private locale: Locale) {}

  validateRequired(value: string | undefined | null): string | null {
    if (!value || value.trim() === "") {
      return this.locale === "zh" ? "此欄位為必填" : "This field is required"
    }
    return null
  }

  validateEmail(value: string): string | null {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(value)) {
      return this.locale === "zh" ? "請輸入有效的電子郵件地址" : "Please enter a valid email address"
    }
    return null
  }

  validateGPA(value: number): string | null {
    if (value < 0 || value > 4.3) {
      return this.locale === "zh" ? "GPA必須在0到4.3之間" : "GPA must be between 0 and 4.3"
    }
    return null
  }

  validateRanking(value: number): string | null {
    if (value < 0 || value > 100) {
      return this.locale === "zh" ? "排名百分比必須在0到100之間" : "Ranking percentage must be between 0 and 100"
    }
    return null
  }
}
