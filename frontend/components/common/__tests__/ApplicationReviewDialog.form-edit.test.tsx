import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import type { Application } from "@/lib/api";
import { ApplicationReviewDialog } from "../ApplicationReviewDialog";

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

const application = (status: string, remark: string) =>
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
      fields: { remark: { field_id: "remark", field_type: "text", value: remark, required: false } },
      documents: [],
    },
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
      .mockResolvedValue({ success: true, message: "", data: application("submitted", "新備註") });
    const user = await openFormTab("college");

    await user.click(screen.getByRole("button", { name: /編輯/ }));
    expect(screen.getByText(/郵局帳號 為學生個人資料/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/郵局帳號/)).not.toBeInTheDocument();

    const remark = screen.getByLabelText("備註");
    await user.clear(remark);
    await user.type(remark, "新備註");
    await user.click(screen.getByRole("button", { name: "儲存" }));

    expect(await screen.findByText("新備註")).toBeInTheDocument();
    expect(updateFormFields).toHaveBeenCalledWith(42, { remark: "新備註" });
    expect(screen.queryByRole("button", { name: "儲存" })).not.toBeInTheDocument();
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
