import { render, screen } from "@testing-library/react";
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

const APPLICATION = {
  id: 42,
  app_id: "APP-114-1-00042",
  status: "submitted",
  academic_year: 114,
  semester: "first",
  scholarship_type: "phd",
  scholarship_name: "博士生獎學金",
  student_name: "王小明",
  student_id: "312551001",
  department_name: "資訊工程學系",
  student_termcount: 3,
  created_at: "2026-09-01T00:00:00Z",
  submitted_form_data: { fields: {}, documents: [] },
  sub_type_labels: { nstc: { zh: "國科會博士生獎學金", en: "NSTC" } },
  professor_review_items: [{ sub_type_code: "nstc", recommendation: "approve" }],
} as unknown as Application;

const renderDialog = (role: "professor" | "college") =>
  render(
    <ApplicationReviewDialog
      application={APPLICATION}
      role={role}
      open
      onOpenChange={() => {}}
      locale="zh"
    />
  );

describe("ApplicationReviewDialog tabs by role", () => {
  beforeEach(() => {
    jest
      .spyOn(api.applications, "getApplicationById")
      .mockResolvedValue({ success: true, message: "", data: APPLICATION });
    jest
      .spyOn(api.applicationFields, "getFormConfig")
      .mockResolvedValue({ success: true, message: "", data: { fields: [], documents: [] } } as never);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("shows the professor the application but not the 學生資訊 / 操作紀錄 tabs", async () => {
    renderDialog("professor");

    expect(await screen.findByRole("tab", { name: /基本資訊/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /表單內容/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /上傳文件/ })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /學生資訊/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /操作紀錄/ })).not.toBeInTheDocument();
    expect(screen.getByRole("tablist")).toHaveClass("grid-cols-3");

    // The 基本資訊 tab keeps its 學生資訊 card.
    expect(screen.getByText("學生資訊")).toBeInTheDocument();
    expect(screen.getByText("王小明")).toBeInTheDocument();
    expect(screen.getByText("312551001")).toBeInTheDocument();

    // 教授審查結果 names the sub-type from the detail response, not its raw code.
    expect(screen.getByText(/國科會博士生獎學金/)).toBeInTheDocument();
    expect(screen.queryByText(/^nstc/)).not.toBeInTheDocument();
  });

  it("keeps the college's 學生資訊 / 操作紀錄 tabs", async () => {
    renderDialog("college");

    expect(await screen.findByRole("tab", { name: /學生資訊/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /操作紀錄/ })).toBeInTheDocument();
    expect(screen.getByRole("tablist")).toHaveClass("grid-cols-5");
  });
});
