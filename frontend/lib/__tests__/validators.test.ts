import { FormValidator } from "../validators";

describe("FormValidator (Simple)", () => {
  describe("Chinese locale", () => {
    let validator: FormValidator;

    beforeEach(() => {
      validator = new FormValidator("zh");
    });

    describe("validateRequired", () => {
      it("should return error for empty string", () => {
        const error = validator.validateRequired("");
        expect(error).toBe("此欄位為必填");
      });

      it("should return error for whitespace only", () => {
        const error = validator.validateRequired("   ");
        expect(error).toBe("此欄位為必填");
      });

      it("should return error for null", () => {
        const error = validator.validateRequired(null);
        expect(error).toBe("此欄位為必填");
      });

      it("should return error for undefined", () => {
        const error = validator.validateRequired(undefined);
        expect(error).toBe("此欄位為必填");
      });

      it("should return null for valid string", () => {
        const error = validator.validateRequired("valid input");
        expect(error).toBeNull();
      });
    });

    describe("validateEmail", () => {
      it("should return error for invalid email format", () => {
        const error = validator.validateEmail("invalid-email");
        expect(error).toBe("請輸入有效的電子郵件地址");
      });

      it("should return error for email without @", () => {
        const error = validator.validateEmail("invalid.email.com");
        expect(error).toBe("請輸入有效的電子郵件地址");
      });

      it("should return error for email without domain", () => {
        const error = validator.validateEmail("invalid@");
        expect(error).toBe("請輸入有效的電子郵件地址");
      });

      it("should return null for valid email", () => {
        const error = validator.validateEmail("test@example.com");
        expect(error).toBeNull();
      });

      it("should return null for complex valid email", () => {
        const error = validator.validateEmail("user.name+tag@example.co.uk");
        expect(error).toBeNull();
      });
    });

    describe("validateGPA", () => {
      it("should return error for GPA below 0", () => {
        const error = validator.validateGPA(-0.1);
        expect(error).toBe("GPA必須在0到4.3之間");
      });

      it("should return error for GPA above 4.3", () => {
        const error = validator.validateGPA(4.4);
        expect(error).toBe("GPA必須在0到4.3之間");
      });

      it("should return null for valid GPA", () => {
        const error = validator.validateGPA(3.5);
        expect(error).toBeNull();
      });

      it("should return null for GPA at boundaries", () => {
        expect(validator.validateGPA(0)).toBeNull();
        expect(validator.validateGPA(4.3)).toBeNull();
      });
    });

    describe("validateRanking", () => {
      it("should return error for ranking below 0", () => {
        const error = validator.validateRanking(-1);
        expect(error).toBe("排名百分比必須在0到100之間");
      });

      it("should return error for ranking above 100", () => {
        const error = validator.validateRanking(101);
        expect(error).toBe("排名百分比必須在0到100之間");
      });

      it("should return null for valid ranking", () => {
        const error = validator.validateRanking(75);
        expect(error).toBeNull();
      });

      it("should return null for ranking at boundaries", () => {
        expect(validator.validateRanking(0)).toBeNull();
        expect(validator.validateRanking(100)).toBeNull();
      });
    });
  });

  describe("English locale", () => {
    let validator: FormValidator;

    beforeEach(() => {
      validator = new FormValidator("en");
    });

    describe("validateRequired", () => {
      it("should return English error message", () => {
        const error = validator.validateRequired("");
        expect(error).toBe("This field is required");
      });
    });

    describe("validateEmail", () => {
      it("should return English error message", () => {
        const error = validator.validateEmail("invalid-email");
        expect(error).toBe("Please enter a valid email address");
      });
    });

    describe("validateGPA", () => {
      it("should return English error message", () => {
        const error = validator.validateGPA(5.0);
        expect(error).toBe("GPA must be between 0 and 4.3");
      });
    });

    describe("validateRanking", () => {
      it("should return English error message", () => {
        const error = validator.validateRanking(150);
        expect(error).toBe("Ranking percentage must be between 0 and 100");
      });
    });
  });
});
