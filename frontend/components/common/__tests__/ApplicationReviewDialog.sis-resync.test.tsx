/**
 * 管理 tab → 重新同步: the dialog reloads the application afterwards, and the reload
 * spinner unmounts <Tabs>. The admin must stay on 管理 and see the card turn 完整
 * (it used to snap back to 基本資訊).
 */
import { render, screen, waitFor } from "@testing-library/react";
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

const application = (termStatus: string) =>
  ({
    id: 182,
    app_id: "APP-115-0-00182",
    status: "submitted",
    academic_year: 115,
    semester: "yearly",
    scholarship_type: "phd",
    scholarship_name: "博士生獎學金",
    student_name: "王小明",
    student_id: "411651009",
    created_at: "2026-10-06T00:00:00Z",
    submitted_form_data: { fields: {}, documents: [] },
    student_data: { std_stdcode: "411651009", _term_data_status: termStatus },
  }) as unknown as Application;

describe("ApplicationReviewDialog 重新同步", () => {
  // The reload is held open so the spinner really replaces <Tabs> before it resolves.
  let finishReload: () => void;

  beforeEach(() => {
    const reloaded = new Promise<void>((resolve) => {
      finishReload = resolve;
    });
    jest
      .spyOn(api.applications, "getApplicationById")
      .mockResolvedValueOnce({ success: true, message: "", data: application("error") })
      .mockImplementation(() =>
        reloaded.then(() => ({ success: true, message: "", data: application("success") }))
      );
    jest
      .spyOn(api.applicationFields, "getFormConfig")
      .mockResolvedValue({ success: true, message: "", data: { fields: [], documents: [] } } as never);
    jest.spyOn(api.admin, "getReviewableSubTypes").mockResolvedValue({ success: true, message: "", data: [] } as never);
    jest.spyOn(api.admin, "getApplicationReview").mockResolvedValue({ success: true, message: "", data: null } as never);
    jest.spyOn(api.admin, "resyncSisTermData").mockResolvedValue({
      success: true,
      message: "已重新同步學籍學期資料",
      data: { id: 182, app_id: "APP-115-0-00182", previous_status: "error", new_status: "success", updated: true },
    } as never);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("stays on 管理 and shows the completed status after the reload", async () => {
    const user = userEvent.setup();
    render(
      <ApplicationReviewDialog
        application={application("error")}
        role="admin"
        open
        onOpenChange={() => {}}
        locale="zh"
      />
    );

    await user.click(await screen.findByRole("tab", { name: /管理/ }));
    expect(await screen.findByText("取得失敗")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /重新同步/ }));

    await waitFor(() => expect(api.applications.getApplicationById).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("tablist")).not.toBeInTheDocument());
    finishReload();

    expect(await screen.findByText("完整")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /管理/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("button", { name: /重新同步/ })).not.toBeInTheDocument();
  });
});
