import {
  isFixedBankDocumentRequired,
  resolveFixedFormText,
  FixedFormText,
} from "../fixed-form-text";
import type { ApplicationField, ApplicationDocument } from "@/lib/api/types";

const DEFAULTS: FixedFormText = {
  fields: {
    postal_account: {
      label: "郵局帳號",
      placeholder: "請輸入 14 碼郵局帳號",
      helpText: "",
    },
    advisor_name: {
      label: "教授姓名",
      placeholder: "請輸入指導教授姓名",
      helpText: "如有超過一位指導教授，請填寫一位主要指導教授。",
    },
    advisor_email: {
      label: "教授 Email",
      placeholder: "professor@nycu.edu.tw",
      helpText: "",
    },
    advisor_nycu_id: {
      label: "人事編號",
      placeholder: "請輸入人事編號",
      helpText: "",
    },
  },
  bankDocument: {
    label: "存摺封面",
    description: "支援格式：JPG, JPEG, PNG, PDF",
  },
};

const field = (overrides: Partial<ApplicationField>): ApplicationField => ({
  id: 0,
  scholarship_type: "phd",
  field_name: "x",
  field_label: "x",
  field_type: "text",
  is_required: true,
  display_order: 1,
  is_active: true,
  created_at: "",
  updated_at: "",
  ...overrides,
});

const document = (
  overrides: Partial<ApplicationDocument>
): ApplicationDocument => ({
  id: 0,
  scholarship_type: "phd",
  document_name: "x",
  is_required: true,
  display_in_list: true,
  requires_upload: true,
  accepted_file_types: [],
  max_file_size: "10MB",
  max_file_count: 1,
  display_order: 1,
  is_active: true,
  created_at: "",
  updated_at: "",
  ...overrides,
});

describe("resolveFixedFormText", () => {
  it("returns the defaults when there is no config yet", () => {
    expect(resolveFixedFormText(null, "zh", DEFAULTS)).toBe(DEFAULTS);
    expect(resolveFixedFormText(undefined, "zh", DEFAULTS)).toBe(DEFAULTS);
  });

  it("uses the admin-edited label, placeholder and help text of a fixed_key row", () => {
    const config = {
      fields: [
        field({
          fixed_key: "postal_account",
          field_label: "郵局局號加帳號（限本人）",
          placeholder: "共 14 碼",
          help_text: "請勿填寫他人帳號",
        }),
      ],
      documents: [],
    };

    const text = resolveFixedFormText(config, "zh", DEFAULTS);

    expect(text.fields.postal_account).toEqual({
      label: "郵局局號加帳號（限本人）",
      placeholder: "共 14 碼",
      helpText: "請勿填寫他人帳號",
    });
    // Keys without a row keep the built-in text.
    expect(text.fields.advisor_name).toEqual(DEFAULTS.fields.advisor_name);
  });

  it("treats a blank 提示文字/說明文字 on the row as cleared, not as unset", () => {
    const config = {
      fields: [
        field({
          fixed_key: "advisor_name",
          field_label: "主要指導教授",
          placeholder: "   ",
          help_text: "",
        }),
      ],
      documents: [],
    };

    const text = resolveFixedFormText(config, "zh", DEFAULTS);

    expect(text.fields.advisor_name).toEqual({
      label: "主要指導教授",
      placeholder: "",
      helpText: "",
    });
  });

  it("keeps the default label when the row's label is blank", () => {
    const config = {
      fields: [field({ fixed_key: "advisor_email", field_label: " " })],
      documents: [],
    };

    expect(
      resolveFixedFormText(config, "zh", DEFAULTS).fields.advisor_email.label
    ).toBe(DEFAULTS.fields.advisor_email.label);
  });

  it("prefers the English column for en and falls back to zh when it is blank", () => {
    const config = {
      fields: [
        field({
          fixed_key: "advisor_email",
          field_label: "教授信箱",
          field_label_en: "Advisor E-mail",
          placeholder: "請輸入信箱",
          placeholder_en: "",
          help_text: "請填學校信箱",
        }),
      ],
      documents: [],
    };

    const text = resolveFixedFormText(config, "en", DEFAULTS);

    expect(text.fields.advisor_email).toEqual({
      label: "Advisor E-mail",
      placeholder: "請輸入信箱",
      helpText: "請填學校信箱",
    });
  });

  it("ignores rows that are not fixed items", () => {
    const config = {
      fields: [
        field({ field_name: "postal_account", field_label: "假的郵局欄位" }),
      ],
      documents: [],
    };

    expect(resolveFixedFormText(config, "zh", DEFAULTS).fields.postal_account).toEqual(
      DEFAULTS.fields.postal_account
    );
  });

  it("uses the renamed 存摺封面 document and its 文件說明", () => {
    const config = {
      fields: [],
      documents: [
        document({
          fixed_key: "bank_statement",
          document_name: "郵局存摺封面影本",
          document_name_en: "Passbook cover copy",
          description: "需含戶名與帳號",
          description_en: "",
        }),
      ],
    };

    expect(resolveFixedFormText(config, "zh", DEFAULTS).bankDocument).toEqual({
      label: "郵局存摺封面影本",
      description: "需含戶名與帳號",
    });
    expect(resolveFixedFormText(config, "en", DEFAULTS).bankDocument).toEqual({
      label: "Passbook cover copy",
      description: "需含戶名與帳號",
    });
  });

  it("keeps the default document text when the config has no bank_statement row", () => {
    expect(
      resolveFixedFormText({ fields: [], documents: [] }, "zh", DEFAULTS)
        .bankDocument
    ).toEqual(DEFAULTS.bankDocument);
  });
});

describe("isFixedBankDocumentRequired", () => {
  it("keeps the built-in default (required) while the config has not loaded", () => {
    expect(isFixedBankDocumentRequired(null)).toBe(true);
    expect(isFixedBankDocumentRequired(undefined)).toBe(true);
  });

  it("treats a loaded config without the row as the admin having deactivated it", () => {
    // The backend always injects the bank_statement row and only drops it
    // from the student payload when is_active is false.
    expect(isFixedBankDocumentRequired({ documents: [] })).toBe(false);
  });

  it("follows the bank_statement row's is_required / is_active", () => {
    const withRow = (overrides: Partial<ApplicationDocument>) => ({
      documents: [document({ fixed_key: "bank_statement", ...overrides })],
    });

    expect(isFixedBankDocumentRequired(withRow({}))).toBe(true);
    expect(isFixedBankDocumentRequired(withRow({ is_required: false }))).toBe(
      false
    );
    expect(isFixedBankDocumentRequired(withRow({ is_active: false }))).toBe(
      false
    );
  });

  it("only reads the fixed bank_statement row, not a same-named admin document", () => {
    expect(
      isFixedBankDocumentRequired({
        documents: [
          document({ document_name: "存摺封面", is_required: true }),
          document({ fixed_key: "bank_statement", is_required: false }),
        ],
      })
    ).toBe(false);
  });
});
