import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { ApplicationFormDataDisplay } from "../application-form-data-display";
import { Locale } from "@/lib/validators";

// Mock the utility functions
jest.mock("@/lib/utils/application-helpers", () => ({
  formatFieldName: jest.fn((fieldName: string, locale: Locale) => {
    const names = {
      zh: {
        name: "姓名",
        email: "電子郵件",
        student_id: "學號",
        department: "系所",
      },
      en: {
        name: "Name",
        email: "Email",
        student_id: "Student ID",
        department: "Department",
      },
    };
    return names[locale][fieldName] || fieldName;
  }),
  formatFieldValue: jest.fn((fieldName: string, value: any, locale: Locale) =>
    Promise.resolve(value)
  ),
  // Re-implement the production formatter so the component still
  // renders objects as JSON (PR #497) under the mock.
  formatDisplayValue: jest.fn((value: unknown) => {
    if (value === null || value === undefined) return "";
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    if (Array.isArray(value)) {
      return value.map(String).join(", ");
    }
    if (typeof value === "object") {
      try {
        return JSON.stringify(value);
      } catch {
        return String(value);
      }
    }
    return String(value);
  }),
}));

// Mock UI components
jest.mock("@/components/ui/label", () => ({
  Label: ({ children, className }: any) => (
    <label data-testid="label" className={className}>
      {children}
    </label>
  ),
}));

describe("ApplicationFormDataDisplay", () => {
  const mockFieldLabels = {
    name: { zh: "姓名", en: "Name" },
    email: { zh: "電子郵件", en: "Email" },
    student_id: { zh: "學號", en: "Student ID" },
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("should render form data with Chinese labels", async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          name: { value: "張三" },
          email: { value: "zhang@nycu.edu.tw" },
          student_id: { value: "12345678" },
        },
      },
    };

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
        fieldLabels={mockFieldLabels}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("姓名")).toBeInTheDocument();
      expect(screen.getByText("張三")).toBeInTheDocument();
      expect(screen.getByText("電子郵件")).toBeInTheDocument();
      expect(screen.getByText("zhang@nycu.edu.tw")).toBeInTheDocument();
    });
  });

  it("should render form data with English labels", async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          name: { value: "John Doe" },
          email: { value: "john@nycu.edu.tw" },
        },
      },
    };

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="en"
        fieldLabels={mockFieldLabels}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Name")).toBeInTheDocument();
      expect(screen.getByText("John Doe")).toBeInTheDocument();
      expect(screen.getByText("Email")).toBeInTheDocument();
      expect(screen.getByText("john@nycu.edu.tw")).toBeInTheDocument();
    });
  });

  it("should show no form data message when form_data structure is used (fallback removed)", async () => {
    const formData = {
      form_data: {
        name: "李四",
        email: "li@nycu.edu.tw",
        department: "CSIE",
      },
    };

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
        fieldLabels={mockFieldLabels}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("無表單資料")).toBeInTheDocument();
    });
  });

  it("should show no form data message when flat object structure is used (fallback removed)", async () => {
    const formData = {
      name: "王五",
      email: "wang@nycu.edu.tw",
      student_id: "87654321",
    };

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
        fieldLabels={mockFieldLabels}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("無表單資料")).toBeInTheDocument();
    });
  });

  it("should skip empty and excluded fields", async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          name: { value: "測試" },
          email: { value: "" }, // Empty value - will show as unfilled
          files: { value: "some_file.pdf" }, // Should be excluded
          agree_terms: { value: true }, // Should be excluded
        },
      },
    };

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
        fieldLabels={mockFieldLabels}
      />
    );

    await waitFor(() => {
      // Filled field should be shown
      expect(screen.getByText("測試")).toBeInTheDocument();

      // Empty field (in fieldLabels but empty value) should show as unfilled
      const emailLabels = screen.getAllByText("電子郵件");
      expect(emailLabels.length).toBeGreaterThan(0);

      // Excluded fields should not appear
      expect(screen.queryByText("some_file.pdf")).not.toBeInTheDocument();
      expect(screen.queryByText("true")).not.toBeInTheDocument();

      // Unfilled message should appear for empty fields (multiple times)
      const unfilledMessages = screen.getAllByText("未填寫");
      expect(unfilledMessages.length).toBeGreaterThan(0);
    });
  });

  it("should show no form data message when form data has no submitted_form_data.fields", async () => {
    const formData = {
      unknown_field: "test value",
    };

    render(<ApplicationFormDataDisplay formData={formData} locale="zh" />);

    await waitFor(() => {
      expect(screen.getByText("無表單資料")).toBeInTheDocument();
    });
  });

  it("should show no form data message when submitted_form_data exists but has no fields", async () => {
    const formData = {
      submitted_form_data: {
        documents: [], // Has documents but no fields
      },
    };

    render(
      <ApplicationFormDataDisplay
        formData={formData}
        locale="zh"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("無表單資料")).toBeInTheDocument();
    });
  });

  it("should handle nested object values by rendering them as JSON", async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          address: {
            value: {
              street: "123 Main St",
              city: "Hsinchu",
              country: "Taiwan",
            },
          },
        },
      },
    };

    render(<ApplicationFormDataDisplay formData={formData} locale="zh" />);

    await waitFor(() => {
      // Plain objects render via JSON.stringify (formatDisplayValue) so the
      // user sees the nested data instead of "[object Object]". The render
      // happens inside <p>...</p> as a single text node, so the substring
      // assertion is enough — no need for individual sub-elements.
      const node = screen.getByText(/123 Main St/);
      expect(node).toBeInTheDocument();
      expect(node.textContent).toMatch(/Hsinchu/);
      expect(node.textContent).toMatch(/Taiwan/);
    });
  });

  it("should handle array values", async () => {
    const formData = {
      submitted_form_data: {
        fields: {
          hobbies: {
            value: ["reading", "coding", "music"],
          },
        },
      },
    };

    render(<ApplicationFormDataDisplay formData={formData} locale="zh" />);

    await waitFor(() => {
      // Should display array as comma-separated values
      expect(screen.getByText(/reading.*coding.*music/)).toBeInTheDocument();
    });
  });

  it("should show loading state initially and then no form data message", () => {
    const formData = {
      name: "Test User",
    };

    render(<ApplicationFormDataDisplay formData={formData} locale="zh" />);

    // Since this doesn't have submitted_form_data.fields, should eventually show no form data message
    // (not currently testing async behavior since it depends on timing)
  });

  // The 郵局帳號 / 指導教授 fixed fields are in every scholarship's form config
  // but live on the student's UserProfile, so the detail response — not
  // submitted_form_data — is where their values come from. See
  // `lib/utils/profile-owned-fields.ts`.
  describe("UserProfile-owned fixed fields", () => {
    const fixedFieldLabels = {
      postal_account: { zh: "郵局帳號", en: "Post Office Account" },
      advisor_name: { zh: "指導教授姓名", en: "Advisor Name" },
      advisor_email: { zh: "指導教授Email", en: "Advisor Email" },
      advisor_nycu_id: { zh: "指導教授本校人事編號", en: "Advisor NYCU ID" },
    };

    it("renders 郵局帳號 once when the submitted snapshot uses the account_number alias", async () => {
      const application = {
        postal_account: "12341234123412",
        submitted_form_data: {
          fields: { account_number: { value: "12341234123412" } },
        },
      };

      render(
        <ApplicationFormDataDisplay
          formData={application}
          locale="zh"
          fieldLabels={fixedFieldLabels}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText("郵局帳號")).toHaveLength(1);
        expect(screen.getByText("12341234123412")).toBeInTheDocument();
      });
    });

    it("renders 郵局帳號 once when the snapshot stores both synonyms", async () => {
      // Submissions from the older wizard carry postal_account AND
      // account_number, both holding the one account the student typed.
      const application = {
        submitted_form_data: {
          fields: {
            postal_account: { value: "12341234123412" },
            account_number: { value: "12341234123412" },
          },
        },
      };

      render(
        <ApplicationFormDataDisplay
          formData={application}
          locale="zh"
          fieldLabels={fixedFieldLabels}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText("郵局帳號")).toHaveLength(1);
        expect(screen.getAllByText("12341234123412")).toHaveLength(1);
      });
    });

    it("renders 指導教授 values from the application instead of 未填寫", async () => {
      const application = {
        advisor_name: "王老師",
        advisor_email: "advisor@nycu.edu.tw",
        advisor_nycu_id: "A12345",
        submitted_form_data: {
          fields: { contact_phone: { value: "0987878978" } },
        },
      };

      render(
        <ApplicationFormDataDisplay
          formData={application}
          locale="zh"
          fieldLabels={fixedFieldLabels}
        />
      );

      await waitFor(() => {
        expect(screen.getByText("王老師")).toBeInTheDocument();
        expect(screen.getByText("advisor@nycu.edu.tw")).toBeInTheDocument();
        expect(screen.getByText("A12345")).toBeInTheDocument();
        // Only 郵局帳號 is genuinely unfilled here.
        expect(screen.getAllByText("未填寫")).toHaveLength(1);
      });
    });

    it("still shows 未填寫 when the student never filled the section in", async () => {
      const application = {
        submitted_form_data: {
          fields: { contact_phone: { value: "0987878978" } },
        },
      };

      render(
        <ApplicationFormDataDisplay
          formData={application}
          locale="zh"
          fieldLabels={fixedFieldLabels}
        />
      );

      await waitFor(() => {
        expect(screen.getAllByText("未填寫")).toHaveLength(4);
      });
    });

    it("does not merge fields the scholarship's form config never declared", async () => {
      // 指導教授 fields are only injected when the scholarship requires
      // professor review; a profile filled in for another scholarship must not
      // add them to this application's form data.
      const application = {
        advisor_name: "王老師",
        postal_account: "12341234123412",
        submitted_form_data: {
          fields: { contact_phone: { value: "0987878978" } },
        },
      };

      render(
        <ApplicationFormDataDisplay
          formData={application}
          locale="zh"
          fieldLabels={{
            postal_account: { zh: "郵局帳號", en: "Post Office Account" },
          }}
        />
      );

      await waitFor(() => {
        expect(screen.getByText("12341234123412")).toBeInTheDocument();
      });
      expect(screen.queryByText("王老師")).not.toBeInTheDocument();
    });

    it("still reports 無表單資料 when nothing was submitted", async () => {
      // A profile value alone is not evidence the student filled a form in.
      const application = {
        postal_account: "12341234123412",
        advisor_name: "王老師",
        submitted_form_data: { fields: {} },
      };

      render(
        <ApplicationFormDataDisplay
          formData={application}
          locale="zh"
          fieldLabels={fixedFieldLabels}
        />
      );

      await waitFor(() => {
        expect(screen.getByText("無表單資料")).toBeInTheDocument();
      });
      expect(screen.queryByText("12341234123412")).not.toBeInTheDocument();
    });

    it("prefers the submitted snapshot over the current profile value", async () => {
      const application = {
        postal_account: "99999999999999",
        submitted_form_data: {
          fields: { account_number: { value: "12341234123412" } },
        },
      };

      render(
        <ApplicationFormDataDisplay
          formData={application}
          locale="zh"
          fieldLabels={fixedFieldLabels}
        />
      );

      await waitFor(() => {
        expect(screen.getByText("12341234123412")).toBeInTheDocument();
        expect(screen.queryByText("99999999999999")).not.toBeInTheDocument();
      });
    });
  });

  it("should handle malformed form data gracefully", async () => {
    const formData = {
      submitted_form_data: {
        fields: null, // Malformed data
      },
    };

    render(<ApplicationFormDataDisplay formData={formData} locale="zh" />);

    await waitFor(() => {
      // Should show no form data message for malformed data
      expect(screen.getByText("無表單資料")).toBeInTheDocument();
    });
  });
});
