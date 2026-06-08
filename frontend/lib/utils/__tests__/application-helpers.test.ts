import {
  formatDate,
  getApplicationTimeline,
  formatFieldName,
  formatFieldValue,
  formatDisplayValue,
  getDocumentLabel,
  fetchApplicationFiles,
  buildApplicationFormFields,
  isValidTaiwanMobile,
  TAIWAN_MOBILE_MESSAGE,
  BadgeVariant,
} from "../application-helpers";
import {
  ApplicationStatus,
  getApplicationStatusLabel,
  getApplicationStatusBadgeVariant,
} from "@/lib/enums";

// Create mock functions that can be reconfigured
const mockGetAll = jest.fn().mockResolvedValue({
  success: true,
  data: [
    {
      id: 1,
      code: "academic_excellence",
      name: "學業優秀獎學金",
      name_en: "Academic Excellence Scholarship",
    },
    {
      id: 2,
      code: "research_grant",
      name: "研究補助",
      name_en: "Research Grant",
    },
  ],
});

const mockGetApplicationById = jest.fn().mockResolvedValue({
  success: true,
  data: {
    id: 1,
    scholarship_type_code: "academic_excellence",
    status: "submitted",
    created_at: "2024-01-01",
    updated_at: "2024-01-02",
    documents: [
      {
        id: "file1",
        filename: "transcript.pdf",
        file_type: "transcript",
      },
    ],
  },
});

const mockGetApplicationFiles = jest.fn().mockResolvedValue({
  success: true,
  data: [
    {
      id: "file1",
      filename: "test.pdf",
      file_type: "transcript",
    },
  ],
});

// Mock the API
jest.mock("@/lib/api", () => ({
  api: {
    scholarships: {
      getAll: (...args: any[]) => mockGetAll(...args),
    },
    applications: {
      getApplicationById: (...args: any[]) => mockGetApplicationById(...args),
      getApplicationFiles: (...args: any[]) => mockGetApplicationFiles(...args),
    },
  },
}));

import { api as mockApi } from "@/lib/api";

// Override mockApi with our mock functions so tests can access them
(mockApi.scholarships.getAll as any) = mockGetAll;
(mockApi.applications.getApplicationById as any) = mockGetApplicationById;
(mockApi.applications.getApplicationFiles as any) = mockGetApplicationFiles;

describe("Application Helpers", () => {
  describe("formatDate", () => {
    it("should format date for Chinese locale", () => {
      const result = formatDate("2025-01-30T10:00:00Z", "zh");
      expect(result).toMatch(/2025/); // Should contain year
    });

    it("should format date for English locale", () => {
      const result = formatDate("2025-01-30T10:00:00Z", "en");
      expect(result).toMatch(/2025/); // Should contain year
    });

    it("should return empty string for null date", () => {
      const result = formatDate(null, "zh");
      expect(result).toBe("");
    });

    it("should return empty string for undefined date", () => {
      const result = formatDate(undefined, "zh");
      expect(result).toBe("");
    });

    it("should return empty string for empty date", () => {
      const result = formatDate("", "zh");
      expect(result).toBe("");
    });
  });

  describe("getApplicationTimeline", () => {
    const mockApplication = {
      status: "submitted",
      review_stage: "student_submitted",
      created_at: "2025-01-01T10:00:00Z",
      submitted_at: "2025-01-02T10:00:00Z",
      reviewed_at: "2025-01-03T10:00:00Z",
      approved_at: "2025-01-04T10:00:00Z",
      // getApplicationTimeline now conditionalizes professor/college review steps
      // on these flags. Tests below expect the full 8-step timeline.
      requires_professor_recommendation: true,
      requires_college_review: true,
    };

    it("should return correct timeline for draft status in Chinese", () => {
      const draftApp = { ...mockApplication, status: "draft", review_stage: "student_draft" };
      const timeline = getApplicationTimeline(draftApp, "zh");

      expect(timeline).toHaveLength(8);
      expect(timeline[0].title).toBe("提交申請");
      expect(timeline[0].status).toBe("current");
      expect(timeline[1].status).toBe("pending");
      expect(timeline[2].status).toBe("pending");
      expect(timeline[3].status).toBe("pending");
      expect(timeline[4].status).toBe("pending");
      expect(timeline[5].status).toBe("pending");
      expect(timeline[6].status).toBe("pending");
      expect(timeline[7].status).toBe("pending");
    });

    it("should return correct timeline for submitted status in English", () => {
      const submittedApp = { ...mockApplication, status: "submitted", review_stage: "student_submitted" };
      const timeline = getApplicationTimeline(submittedApp, "en");

      expect(timeline).toHaveLength(8);
      expect(timeline[0].title).toBe("Submit Application");
      expect(timeline[0].status).toBe("completed");
      expect(timeline[1].title).toContain("Waiting for Professor Review");
      expect(timeline[1].status).toBe("current");
      expect(timeline[2].title).toBe("Professor Reviewing");
      expect(timeline[2].status).toBe("pending");
    });

    it("should return correct timeline for approved status", () => {
      const approvedApp = { ...mockApplication, status: "approved", review_stage: "completed" };
      const timeline = getApplicationTimeline(approvedApp, "zh");

      expect(timeline[0].status).toBe("completed");
      expect(timeline[7].status).toBe("completed");
    });

    it("should return correct timeline for rejected status", () => {
      const rejectedApp = { ...mockApplication, status: "rejected", review_stage: "college_reviewed" };
      const timeline = getApplicationTimeline(rejectedApp, "zh");

      expect(timeline[0].status).toBe("completed");
      expect(timeline[7].status).toBe("rejected");
    });
  });

  describe("getApplicationStatusBadgeVariant", () => {
    it("should return correct colors for different statuses", () => {
      expect(getApplicationStatusBadgeVariant(ApplicationStatus.DRAFT)).toBe("secondary");
      expect(getApplicationStatusBadgeVariant(ApplicationStatus.SUBMITTED)).toBe("default");
      expect(getApplicationStatusBadgeVariant(ApplicationStatus.UNDER_REVIEW)).toBe("outline");
      expect(getApplicationStatusBadgeVariant(ApplicationStatus.APPROVED)).toBe("default");
      expect(getApplicationStatusBadgeVariant(ApplicationStatus.REJECTED)).toBe("destructive");
      expect(getApplicationStatusBadgeVariant(ApplicationStatus.WITHDRAWN)).toBe("secondary");
    });
  });

  describe("getApplicationStatusLabel", () => {
    it("should return Chinese status names", () => {
      expect(getApplicationStatusLabel(ApplicationStatus.DRAFT, "zh")).toBe("草稿");
      expect(getApplicationStatusLabel(ApplicationStatus.SUBMITTED, "zh")).toBe("已送出");
      expect(getApplicationStatusLabel(ApplicationStatus.UNDER_REVIEW, "zh")).toBe("審批中");
      expect(getApplicationStatusLabel(ApplicationStatus.APPROVED, "zh")).toBe("已核准");
      expect(getApplicationStatusLabel(ApplicationStatus.REJECTED, "zh")).toBe("已駁回");
    });

    it("should return English status names", () => {
      expect(getApplicationStatusLabel(ApplicationStatus.DRAFT, "en")).toBe("Draft");
      expect(getApplicationStatusLabel(ApplicationStatus.SUBMITTED, "en")).toBe("Submitted");
      expect(getApplicationStatusLabel(ApplicationStatus.UNDER_REVIEW, "en")).toBe("Under Review");
      expect(getApplicationStatusLabel(ApplicationStatus.APPROVED, "en")).toBe("Approved");
      expect(getApplicationStatusLabel(ApplicationStatus.REJECTED, "en")).toBe("Rejected");
    });
  });

  describe("formatFieldName", () => {
    it("should return Chinese field names", () => {
      expect(formatFieldName("academic_year", "zh")).toBe("學年度");
      expect(formatFieldName("gpa", "zh")).toBe("學期平均成績");
      expect(formatFieldName("contact_phone", "zh")).toBe("聯絡電話");
      expect(formatFieldName("bank_account", "zh")).toBe("銀行帳戶");
    });

    it("should return English field names", () => {
      expect(formatFieldName("academic_year", "en")).toBe("Academic Year");
      expect(formatFieldName("gpa", "en")).toBe("GPA");
      expect(formatFieldName("contact_phone", "en")).toBe("Contact Phone");
      expect(formatFieldName("bank_account", "en")).toBe("Bank Account");
    });

    it("should return original field name if not mapped", () => {
      expect(formatFieldName("unknown_field", "zh")).toBe("unknown_field");
      expect(formatFieldName("unknown_field", "en")).toBe("unknown_field");
    });
  });

  describe("formatFieldValue", () => {
    beforeEach(() => {
      jest.clearAllMocks();
    });

    it("should format scholarship type from API response", async () => {
      mockApi.scholarships.getAll.mockResolvedValue({
        success: true,
        data: [
          {
            code: "academic_excellence",
            name: "學業優秀獎學金",
            name_en: "Academic Excellence Scholarship",
          },
        ],
      });

      const result = await formatFieldValue(
        "scholarship_type",
        "academic_excellence",
        "zh"
      );
      expect(result).toBe("學業優秀獎學金");

      const resultEn = await formatFieldValue(
        "scholarship_type",
        "academic_excellence",
        "en"
      );
      expect(resultEn).toBe("Academic Excellence Scholarship");
    });

    it("should return code if scholarship not found in API", async () => {
      mockApi.scholarships.getAll.mockResolvedValue({
        success: true,
        data: [],
      });

      const result = await formatFieldValue(
        "scholarship_type",
        "unknown_code",
        "zh"
      );
      expect(result).toBe("unknown_code");
    });

    it("should return code if API fails", async () => {
      mockApi.scholarships.getAll.mockRejectedValue(new Error("API Error"));

      const result = await formatFieldValue(
        "scholarship_type",
        "academic_excellence",
        "zh"
      );
      expect(result).toBe("academic_excellence");
    });

    it("should return value as-is for non-scholarship fields", async () => {
      const result = await formatFieldValue("gpa", "3.5", "zh");
      expect(result).toBe("3.5");
    });
  });

  describe("getDocumentLabel", () => {
    it("should use dynamic label when provided", () => {
      const dynamicLabel = { zh: "動態標籤", en: "Dynamic Label" };

      expect(getDocumentLabel("transcript", "zh", dynamicLabel)).toBe(
        "動態標籤"
      );
      expect(getDocumentLabel("transcript", "en", dynamicLabel)).toBe(
        "Dynamic Label"
      );
    });

    it("should fallback to Chinese label when English not available", () => {
      const dynamicLabel = { zh: "中文標籤" };

      expect(getDocumentLabel("transcript", "en", dynamicLabel)).toBe(
        "中文標籤"
      );
    });

    it("should use static labels when no dynamic label provided", () => {
      expect(getDocumentLabel("transcript", "zh")).toBe("成績單");
      expect(getDocumentLabel("transcript", "en")).toBe("Academic Transcript");
      expect(getDocumentLabel("research_proposal", "zh")).toBe("研究計畫書");
      expect(getDocumentLabel("cv", "en")).toBe("CV/Resume");
    });

    it("should return original docType if not mapped", () => {
      expect(getDocumentLabel("unknown_doc", "zh")).toBe("unknown_doc");
      expect(getDocumentLabel("unknown_doc", "en")).toBe("unknown_doc");
    });
  });

  describe("fetchApplicationFiles", () => {
    beforeEach(() => {
      jest.clearAllMocks();
    });

    it("should fetch files from application details", async () => {
      const mockDocuments = [
        {
          file_id: "file1",
          filename: "transcript.pdf",
          original_filename: "my_transcript.pdf",
          file_size: 1024,
          mime_type: "application/pdf",
          document_type: "transcript",
          file_path: "/files/transcript.pdf",
          download_url: "http://example.com/download/file1",
          is_verified: true,
          upload_time: "2025-01-01T10:00:00Z",
        },
      ];

      mockApi.applications.getApplicationById.mockResolvedValue({
        success: true,
        data: {
          submitted_form_data: {
            documents: mockDocuments,
          },
        },
      });

      const result = await fetchApplicationFiles(1);

      expect(result).toHaveLength(1);
      expect(result[0]).toEqual({
        id: "file1",
        filename: "transcript.pdf",
        original_filename: "my_transcript.pdf",
        file_size: 1024,
        mime_type: "application/pdf",
        file_type: "transcript",
        file_path: "/files/transcript.pdf",
        download_url: "http://example.com/download/file1",
        is_verified: true,
        uploaded_at: "2025-01-01T10:00:00Z",
      });
    });

    it("should fallback to files API if no documents in application details", async () => {
      mockApi.applications.getApplicationById.mockResolvedValue({
        success: true,
        data: {
          submitted_form_data: {},
        },
      });

      const mockFiles = [
        { id: "file1", filename: "test.pdf", file_type: "transcript" },
      ];

      mockApi.applications.getApplicationFiles.mockResolvedValue({
        success: true,
        data: mockFiles,
      });

      const result = await fetchApplicationFiles(1);
      expect(result).toEqual(mockFiles);
    });

    it("should return empty array if both APIs fail", async () => {
      mockApi.applications.getApplicationById.mockRejectedValue(
        new Error("API Error")
      );
      mockApi.applications.getApplicationFiles.mockRejectedValue(
        new Error("API Error")
      );

      const result = await fetchApplicationFiles(1);
      expect(result).toEqual([]);
    });

    it("should return empty array if no files found", async () => {
      mockApi.applications.getApplicationById.mockResolvedValue({
        success: true,
        data: { submitted_form_data: {} },
      });

      mockApi.applications.getApplicationFiles.mockResolvedValue({
        success: false,
        data: null,
      });

      const result = await fetchApplicationFiles(1);
      expect(result).toEqual([]);
    });
  });

  describe("formatDisplayValue", () => {
    // The display formatter is the contract that
    // application-form-data-display.tsx leans on to avoid rendering
    // "[object Object]" for nested form-field values.
    it("returns empty string for null/undefined", () => {
      expect(formatDisplayValue(null)).toBe("");
      expect(formatDisplayValue(undefined)).toBe("");
    });

    it("returns the input unchanged for strings (including empty)", () => {
      expect(formatDisplayValue("")).toBe("");
      expect(formatDisplayValue("hello")).toBe("hello");
      expect(formatDisplayValue("0")).toBe("0");
    });

    it("stringifies numeric values, preserving 0 and negatives", () => {
      expect(formatDisplayValue(0)).toBe("0");
      expect(formatDisplayValue(42)).toBe("42");
      expect(formatDisplayValue(-1.5)).toBe("-1.5");
    });

    it("stringifies booleans", () => {
      expect(formatDisplayValue(true)).toBe("true");
      expect(formatDisplayValue(false)).toBe("false");
    });

    it("renders arrays as comma-separated values", () => {
      // The existing array-rendering test in
      // application-form-data-display.test.tsx pins this exact shape.
      expect(formatDisplayValue(["reading", "coding", "music"])).toBe(
        "reading, coding, music"
      );
    });

    it("renders plain objects as JSON instead of [object Object]", () => {
      // The original bug: String({...}) → "[object Object]".
      expect(
        formatDisplayValue({ street: "123 Main St", city: "Hsinchu" })
      ).toBe('{"street":"123 Main St","city":"Hsinchu"}');
    });

    it("renders nested objects recursively via JSON.stringify", () => {
      expect(
        formatDisplayValue({ address: { city: "Hsinchu" } })
      ).toBe('{"address":{"city":"Hsinchu"}}');
    });

    it("recursively formats arrays of objects", () => {
      expect(
        formatDisplayValue([{ a: 1 }, { b: 2 }])
      ).toBe('{"a":1}, {"b":2}');
    });

    it("falls back to String(value) when JSON.stringify throws (e.g. cycles)", () => {
      const cyclic: any = { a: 1 };
      cyclic.self = cyclic;
      // Should not throw, and should return a defined string.
      const result = formatDisplayValue(cyclic);
      expect(typeof result).toBe("string");
      expect(result.length).toBeGreaterThan(0);
    });
  });
});

describe("buildApplicationFormFields", () => {
  it("wraps dynamic form values into submitted_form_data field entries", () => {
    const fields = buildApplicationFormFields(
      { contact_phone: "0978789789", master_school_info: "nycucs" },
      ""
    );

    expect(fields.contact_phone).toEqual({
      field_id: "contact_phone",
      field_type: "text",
      value: "0978789789",
      required: true,
    });
    expect(fields.master_school_info.value).toBe("nycucs");
  });

  it("includes the postal account number so admins and bank verification can see it", () => {
    const fields = buildApplicationFormFields({}, "70000121234567");

    // Backend extract_bank_fields_from_application looks up the "account_number" key.
    expect(fields.account_number).toEqual({
      field_id: "account_number",
      field_type: "text",
      value: "70000121234567",
      required: true,
    });
  });

  it("trims surrounding whitespace from the account number", () => {
    const fields = buildApplicationFormFields({}, "  70000121234567  ");
    expect(fields.account_number.value).toBe("70000121234567");
  });

  it("omits account_number when no account is provided", () => {
    expect(buildApplicationFormFields({}, "")).not.toHaveProperty(
      "account_number"
    );
    expect(buildApplicationFormFields({}, undefined)).not.toHaveProperty(
      "account_number"
    );
    expect(buildApplicationFormFields({}, "   ")).not.toHaveProperty(
      "account_number"
    );
  });

  it("stringifies non-string dynamic values", () => {
    const fields = buildApplicationFormFields({ completed_terms: 4 }, "");
    expect(fields.completed_terms.value).toBe("4");
  });

  it("lets the dedicated account state win over a stale dynamic account_number key", () => {
    // Editing a draft can surface a previously folded account_number as a
    // dynamic key; the dedicated state must take precedence on re-save.
    const fields = buildApplicationFormFields(
      { account_number: "OLD" },
      "70000121234567"
    );
    expect(fields.account_number.value).toBe("70000121234567");
  });
});

describe("formatFieldName - postal account label", () => {
  it("labels account_number as the post office account", () => {
    expect(formatFieldName("account_number", "zh")).toBe("郵局帳號");
    expect(formatFieldName("account_number", "en")).toBe("Post Office Account");
  });
});

describe("isValidTaiwanMobile", () => {
  it("accepts a 09-prefixed 10-digit number", () => {
    expect(isValidTaiwanMobile("0912345678")).toBe(true);
  });

  it("rejects landline / dashed formats", () => {
    expect(isValidTaiwanMobile("0912-345-678")).toBe(false);
    expect(isValidTaiwanMobile("02-12345678")).toBe(false);
  });

  it("rejects wrong length", () => {
    expect(isValidTaiwanMobile("091234567")).toBe(false);
    expect(isValidTaiwanMobile("09123456789")).toBe(false);
  });

  it("rejects a non-09 prefix and non-digits", () => {
    expect(isValidTaiwanMobile("0812345678")).toBe(false);
    expect(isValidTaiwanMobile("09abcd5678")).toBe(false);
  });

  it("rejects empty / non-string input", () => {
    expect(isValidTaiwanMobile("")).toBe(false);
    expect(isValidTaiwanMobile(undefined)).toBe(false);
    expect(isValidTaiwanMobile(null)).toBe(false);
    expect(isValidTaiwanMobile(912345678)).toBe(false);
  });

  it("exposes the requested help message", () => {
    expect(TAIWAN_MOBILE_MESSAGE).toBe("請輸入本人有效的台灣手機 (09xxxxxx)");
  });
});
