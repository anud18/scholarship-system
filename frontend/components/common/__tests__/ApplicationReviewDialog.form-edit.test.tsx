import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import api from "@/lib/api";
import type { Application } from "@/lib/api";
import { ApplicationReviewDialog } from "../ApplicationReviewDialog";

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn(), warning: jest.fn() },
}));

jest.mock("@/hooks/use-reference-data", () => ({
  ...jest.requireActual("@/hooks/use-reference-data"),
  useReferenceData: () => ({
    studyingStatuses: [],
    degrees: [],
    departments: [],
    genders: [],
    academies: [],
    identities: [],
    schoolIdentities: [],
    enrollTypes: [],
  }),
}));

jest.mock("@/components/application-audit-trail", () => ({
  ApplicationAuditTrail: () => null,
}));

const OWN_ACCOUNT = "11111111111111";
const LEAKED_ACCOUNT = "99999999999999";

const application = (status: string, remark: string, overrides: Record<string, unknown> = {}) =>
  ({
    id: 42,
    app_id: "APP-114-1-00042",
    status,
    academic_year: 114,
    semester: "first",
    scholarship_type: "phd",
    scholarship_name: "博士生獎學金",
    student_name: "王小明",
    created_at: "2026-09-01T00:00:00Z",
    submitted_form_data: {
      fields: {
        remark: { field_id: "remark", field_type: "text", value: remark, required: false },
        account_number: { field_id: "account_number", field_type: "text", value: OWN_ACCOUNT },
        postal_account: { field_id: "postal_account", field_type: "text", value: LEAKED_ACCOUNT },
        advisor_name: { field_id: "advisor_name", field_type: "text", value: "外洩教授" },
      },
      documents: [],
    },
    postal_account: "22222222222222",
    advisor_name: "王教授",
    advisor_email: "wang@nycu.edu.tw",
    advisor_nycu_id: "P0001",
    ...overrides,
  }) as unknown as Application;

const configField = (field_name: string, field_label: string, extra: Record<string, unknown> = {}) => ({
  id: 0,
  scholarship_type: "phd",
  field_name,
  field_label,
  field_type: "text",
  is_required: false,
  is_active: true,
  display_order: 0,
  ...extra,
});

const FORM_CONFIG = {
  fields: [
    configField("remark", "備註"),
    configField("postal_account", "郵局帳號", { fixed_key: "postal_account", is_required: true }),
    configField("advisor_name", "教授姓名", { fixed_key: "advisor_name", is_required: true }),
    configField("advisor_email", "教授 Email", { fixed_key: "advisor_email", field_type: "email" }),
    configField("advisor_nycu_id", "人事編號", { fixed_key: "advisor_nycu_id", is_required: true }),
  ],
  documents: [],
};

const openFormTab = async (role: "professor" | "college" | "admin", status = "submitted") => {
  jest
    .spyOn(api.applications, "getApplicationById")
    .mockResolvedValue({ success: true, message: "", data: application(status, "舊備註") });
  jest
    .spyOn(api.applicationFields, "getFormConfig")
    .mockResolvedValue({ success: true, message: "", data: FORM_CONFIG } as never);
  jest.spyOn(api.admin, "getReviewableSubTypes").mockResolvedValue({ success: true, message: "", data: [] } as never);
  jest.spyOn(api.admin, "getApplicationReview").mockResolvedValue({ success: true, message: "", data: null } as never);

  const user = userEvent.setup();
  render(
    <ApplicationReviewDialog
      application={application(status, "舊備註")}
      role={role}
      open
      onOpenChange={() => {}}
      locale="zh"
    />
  );
  await user.click(await screen.findByRole("tab", { name: /表單內容/ }));
  await screen.findByText("舊備註");
  return user;
};

describe("ApplicationReviewDialog 表單內容編輯", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("lets college staff edit a field and shows the saved value", async () => {
    const updateFormFields = jest
      .spyOn(api.applications, "updateFormFields")
      .mockResolvedValue({ success: true, message: "表單內容已更新", data: application("submitted", "新備註") });
    const user = await openFormTab("college");

    await user.click(screen.getByRole("button", { name: /編輯/ }));
    const remark = screen.getByLabelText("備註");
    await user.clear(remark);
    await user.type(remark, "新備註");
    await user.click(screen.getByRole("button", { name: "儲存" }));

    expect(await screen.findByText("新備註")).toBeInTheDocument();
    expect(updateFormFields).toHaveBeenCalledWith(42, { remark: "新備註" });
    expect(screen.queryByRole("button", { name: "儲存" })).not.toBeInTheDocument();
  });

  it("opens the account and advisor fields at the values the dialog shows", async () => {
    const user = await openFormTab("admin");

    await user.click(screen.getByRole("button", { name: /編輯/ }));

    expect(screen.queryByText(/無法在此修改/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/郵局帳號/)).toHaveValue(OWN_ACCOUNT);
    expect(screen.getByLabelText(/教授姓名/)).toHaveValue("王教授");
    expect(screen.getByLabelText(/教授 Email/)).toHaveValue("wang@nycu.edu.tw");
    expect(screen.getByLabelText(/人事編號/)).toHaveValue("P0001");
  });

  it("shows the saved advisor and the backend's message after saving", async () => {
    const saved = application("submitted", "舊備註", { advisor_nycu_id: "P0002", professor_id: 7 });
    const updateFormFields = jest
      .spyOn(api.applications, "updateFormFields")
      .mockResolvedValue({ success: true, message: "表單內容已更新，審核教授已改派為 李教授", data: saved });
    const user = await openFormTab("admin");

    await user.click(screen.getByRole("button", { name: /編輯/ }));
    const nycuId = screen.getByLabelText(/人事編號/);
    await user.clear(nycuId);
    await user.type(nycuId, "P0002");
    await user.click(screen.getByRole("button", { name: "儲存" }));

    expect(await screen.findByText("P0002")).toBeInTheDocument();
    expect(updateFormFields).toHaveBeenCalledWith(42, { advisor_nycu_id: "P0002" });
    expect(toast.success).toHaveBeenCalledWith("表單內容已更新，審核教授已改派為 李教授");
  });

  it("gives the professor no 編輯 button", async () => {
    await openFormTab("professor");
    expect(screen.queryByRole("button", { name: /編輯/ })).not.toBeInTheDocument();
  });

  it("gives staff no 編輯 button while the student owns the form", async () => {
    await openFormTab("admin", "returned");
    expect(screen.queryByRole("button", { name: /編輯/ })).not.toBeInTheDocument();
  });
});
