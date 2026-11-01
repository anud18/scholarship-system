import { fireEvent, render, screen } from "@testing-library/react";
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

const BASE_APPLICATION = {
  id: 42,
  app_id: "APP-114-1-00042",
  status: "submitted",
  academic_year: 114,
  semester: "first",
  scholarship_type: "phd",
  scholarship_name: "博士生獎學金",
  student_name: "王小明",
  student_id: "312551001",
  created_at: "2026-09-01T00:00:00Z",
  submitted_form_data: { fields: {}, documents: [] },
} as unknown as Application;

const renderDialog = (
  application: Application,
  onDelete?: (app: Application) => void
) =>
  render(
    <ApplicationReviewDialog
      application={application}
      role="college"
      open
      onOpenChange={() => {}}
      locale="zh"
      onDelete={onDelete}
    />
  );

describe("ApplicationReviewDialog 刪除申請 (學院承辦人)", () => {
  beforeEach(() => {
    jest
      .spyOn(api.applications, "getApplicationById")
      .mockResolvedValue({ success: true, message: "", data: BASE_APPLICATION });
    jest
      .spyOn(api.applicationFields, "getFormConfig")
      .mockResolvedValue({ success: true, message: "", data: { fields: [], documents: [] } } as never);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("offers 刪除申請 for a deletable row and hands back the list row", async () => {
    const onDelete = jest.fn();
    const row = { ...BASE_APPLICATION, is_deletable: true } as Application;
    renderDialog(row, onDelete);

    fireEvent.click(await screen.findByRole("button", { name: /刪除申請/ }));

    expect(onDelete).toHaveBeenCalledWith(row);
  });

  it("still offers 刪除申請 when the detail fetch fails (only the list row is needed)", async () => {
    jest
      .spyOn(api.applications, "getApplicationById")
      .mockResolvedValue({ success: false, message: "SIS 逾時", data: undefined } as never);
    const onDelete = jest.fn();
    const row = { ...BASE_APPLICATION, is_deletable: true } as Application;
    renderDialog(row, onDelete);

    fireEvent.click(await screen.findByRole("button", { name: /刪除申請/ }));

    expect(onDelete).toHaveBeenCalledWith(row);
  });

  it("hides 刪除申請 once the application has entered 分發階段", async () => {
    renderDialog({ ...BASE_APPLICATION, is_deletable: false } as Application, jest.fn());

    expect(await screen.findByRole("tab", { name: /基本資訊/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /刪除申請/ })).not.toBeInTheDocument();
  });

  it("hides 刪除申請 when the host does not wire onDelete", async () => {
    renderDialog({ ...BASE_APPLICATION, is_deletable: true } as Application);

    expect(await screen.findByRole("tab", { name: /基本資訊/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /刪除申請/ })).not.toBeInTheDocument();
  });
});
