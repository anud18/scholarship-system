import { FormValidator, ValidationResult } from "../validation";

// Mock the i18n module
jest.mock("@/lib/i18n", () => ({
  getTranslation: jest.fn((locale: string, key: string) => {
    // Simple mock translations for testing
    const translations: { [locale: string]: { [key: string]: string } } = {
      zh: {
        "gpa.required": "請輸入GPA",
        "gpa.invalid": "GPA必須在0-4之間",
      },
      en: {
        "gpa.required": "Please enter GPA",
        "gpa.invalid": "GPA must be between 0-4",
      },
    };
    return translations[locale]?.[key] || key;
  }),
}));

describe("FormValidator", () => {
  describe("Chinese locale", () => {
    let validator: FormValidator;

    beforeEach(() => {
      validator = new FormValidator("zh");
    });

    describe("validateGPA", () => {
      it("should return error for empty GPA", () => {
        const result = validator.validateGPA("", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入GPA");
      });

      it("should return error for invalid GPA format", () => {
        const result = validator.validateGPA("invalid", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("GPA必須在0-4之間");
      });

      it("should return error for GPA below 0", () => {
        const result = validator.validateGPA("-0.5", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("GPA必須在0-4之間");
      });

      it("should return error for GPA above 4", () => {
        const result = validator.validateGPA("4.5", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("GPA必須在0-4之間");
      });

      it("should return warning for undergraduate GPA below 3.38", () => {
        const result = validator.validateGPA("3.2", "undergraduate");
        expect(result.isValid).toBe(true);
        expect(result.warning).toBe("GPA低於標準3.38，建議提供排名證明");
      });

      it("should return info for excellent GPA", () => {
        const result = validator.validateGPA("3.9", "undergraduate");
        expect(result.isValid).toBe(true);
        expect(result.info).toBe("優秀的學業表現！");
      });

      it("should return valid for normal GPA", () => {
        const result = validator.validateGPA("3.5", "undergraduate");
        expect(result.isValid).toBe(true);
        expect(result.warning).toBeUndefined();
        expect(result.info).toBeUndefined();
      });
    });

    describe("validateRanking", () => {
      it("should return error for empty ranking", () => {
        const result = validator.validateRanking("", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入排名百分比");
      });

      it("should return error for invalid ranking format", () => {
        const result = validator.validateRanking("invalid", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("排名百分比必須在0-100之間");
      });

      it("should return error for ranking below 0", () => {
        const result = validator.validateRanking("-5", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("排名百分比必須在0-100之間");
      });

      it("should return error for ranking above 100", () => {
        const result = validator.validateRanking("105", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("排名百分比必須在0-100之間");
      });

      it("should return error for undergraduate ranking above 35%", () => {
        const result = validator.validateRanking("40", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("排名需在前35%以內");
      });

      it("should return info for top 10% ranking", () => {
        const result = validator.validateRanking("8", "undergraduate");
        expect(result.isValid).toBe(true);
        expect(result.info).toBe("前10%排名，符合優秀學生標準");
      });

      it("should return valid for acceptable ranking", () => {
        const result = validator.validateRanking("25", "undergraduate");
        expect(result.isValid).toBe(true);
        expect(result.error).toBeUndefined();
      });
    });

    describe("validateTermCount", () => {
      it("should return error for empty term count", () => {
        const result = validator.validateTermCount("", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入修習學期數");
      });

      it("should return error for invalid term count format", () => {
        const result = validator.validateTermCount("invalid", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("修習學期數必須大於0");
      });

      it("should return error for term count less than 1", () => {
        const result = validator.validateTermCount("0", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("修習學期數必須大於0");
      });

      it("should return error for undergraduate term count exceeding 6", () => {
        const result = validator.validateTermCount("7", "undergraduate");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("學士班新生獎學金修習學期數不得超過6學期");
      });

      it("should return error for PhD term count exceeding 2", () => {
        const result = validator.validateTermCount("3", "phd");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("博士生研究獎學金修習學期數不得超過2學期");
      });

      it("should return valid for acceptable term count", () => {
        const result = validator.validateTermCount("4", "undergraduate");
        expect(result.isValid).toBe(true);
      });
    });

    describe("validatePhone", () => {
      it("should return error for empty phone", () => {
        const result = validator.validatePhone("");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入連絡電話");
      });

      it("should accept valid mobile format", () => {
        const result = validator.validatePhone("0912345678");
        expect(result.isValid).toBe(true);
      });

      it("should accept valid landline format", () => {
        const result = validator.validatePhone("02-12345678");
        expect(result.isValid).toBe(true);
      });

      it("should return error for invalid phone format", () => {
        const result = validator.validatePhone("123456");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入有效的電話號碼格式");
      });
    });

    describe("validateBankAccount", () => {
      it("should return error for empty bank account", () => {
        const result = validator.validateBankAccount("");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入銀行帳號");
      });

      it("should return error for account too short", () => {
        const result = validator.validateBankAccount("123456789");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("銀行帳號長度應在10-16位數之間");
      });

      it("should return error for account too long", () => {
        const result = validator.validateBankAccount("12345678901234567");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("銀行帳號長度應在10-16位數之間");
      });

      it("should return error for non-numeric account", () => {
        const result = validator.validateBankAccount("1234567890a");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("銀行帳號只能包含數字");
      });

      it("should accept valid bank account", () => {
        const result = validator.validateBankAccount("1234567890123");
        expect(result.isValid).toBe(true);
      });
    });

    describe("validateEmail", () => {
      it("should return error for empty email", () => {
        const result = validator.validateEmail("");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入電子郵件");
      });

      it("should return error for invalid email format", () => {
        const result = validator.validateEmail("invalid-email");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入有效的電子郵件格式");
      });

      it("should accept valid email", () => {
        const result = validator.validateEmail("test@example.com");
        expect(result.isValid).toBe(true);
      });
    });

    describe("validateAddress", () => {
      it("should return error for empty address", () => {
        const result = validator.validateAddress("");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入通訊地址");
      });

      it("should return error for address too short", () => {
        const result = validator.validateAddress("短地址");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("地址長度過短，請輸入完整地址");
      });

      it("should accept valid address", () => {
        const result =
          validator.validateAddress("台北市大安區羅斯福路四段一號");
        expect(result.isValid).toBe(true);
      });
    });

    describe("validateResearchProposal", () => {
      it("should return error for empty proposal", () => {
        const result = validator.validateResearchProposal("");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("請輸入研究計畫摘要");
      });

      it("should return error for proposal too short", () => {
        const result = validator.validateResearchProposal("Too short");
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("研究計畫摘要至少需要100字");
      });

      it("should return error for proposal too long", () => {
        const longText = "a".repeat(2001);
        const result = validator.validateResearchProposal(longText);
        expect(result.isValid).toBe(false);
        expect(result.error).toBe("研究計畫摘要不得超過2000字");
      });

      it("should accept valid proposal", () => {
        const validText =
          "This is a valid research proposal that meets the minimum length requirement of 100 characters and provides meaningful content about the research project.";
        const result = validator.validateResearchProposal(validText);
        expect(result.isValid).toBe(true);
      });
    });
  });

  describe("English locale", () => {
    let validator: FormValidator;

    beforeEach(() => {
      validator = new FormValidator("en");
    });

    it("should return English error messages", () => {
      const result = validator.validateGPA("", "undergraduate");
      expect(result.isValid).toBe(false);
      expect(result.error).toBe("Please enter GPA");
    });

    it("should return English warning messages", () => {
      const result = validator.validateGPA("3.2", "undergraduate");
      expect(result.isValid).toBe(true);
      expect(result.warning).toBe(
        "GPA below 3.38 standard, ranking proof recommended"
      );
    });

    it("should return English info messages", () => {
      const result = validator.validateGPA("3.9", "undergraduate");
      expect(result.isValid).toBe(true);
      expect(result.info).toBe("Excellent academic performance!");
    });
  });
});
