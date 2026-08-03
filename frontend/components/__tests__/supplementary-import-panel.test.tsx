/**
 * Tests for `SupplementaryImportPanel` — the college-facing 補充匯入 tab that
 * replaced 批次匯入 for colleges.
 *
 * What's pinned:
 * - Mounts and fetches the scholarship list.
 * - The period selector stays disabled until a scholarship is chosen (the
 *   availability check needs both to address a ScholarshipConfiguration).
 * - The drop zone is disabled while the period is not open for 補充匯入 —
 *   the whole point of the availability endpoint is to explain that BEFORE
 *   the college picks a file and eats a 403.
 * - The copy states that rank comes from the ordinary ranking flow, which is
 *   the behaviour change this feature is about.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SupplementaryImportPanel } from "../supplementary-import-panel";
import { apiClient } from "@/lib/api";

// NOTE: We do NOT jest.mock("@/lib/api") — under this repo's native-ESM jest
// setup a factory mock does not intercept the component's import. Spying on
// the real singleton's namespace objects works because they are the same
// objects the component reaches at runtime.

const SCHOLARSHIP = { id: 7, name: "博士生獎學金", name_en: "PhD", code: "phd" };
const PERIOD = {
  value: "114-yearly",
  academic_year: 114,
  semester: null,
  label: "114 學年度",
  label_en: "AY114",
  is_current: true,
  cycle: "yearly",
  sort_order: 1,
};

function mockApis({ allowed }: { allowed: boolean }) {
  jest
    .spyOn(apiClient.admin, "getMyScholarships")
    .mockResolvedValue({ success: true, data: [SCHOLARSHIP] } as any);
  jest.spyOn(apiClient.referenceData, "getScholarshipPeriods").mockResolvedValue({
    success: true,
    data: { periods: [PERIOD], cycle: "yearly" },
  } as any);
  jest
    .spyOn(apiClient.college, "getSupplementaryImportAvailability")
    .mockResolvedValue({
      success: true,
      data: { allowed, configuration_id: 42 },
    } as any);
  jest
    .spyOn(apiClient.college, "downloadSupplementaryImportTemplate")
    .mockResolvedValue({
      blob: new Blob(["x"]),
      filename: "114學年度博士生獎學金補充匯入範本.xlsx",
    } as any);
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("SupplementaryImportPanel", () => {
  it("fetches the college's scholarships on mount", async () => {
    mockApis({ allowed: true });
    render(<SupplementaryImportPanel />);
    await waitFor(() => {
      expect(apiClient.admin.getMyScholarships).toHaveBeenCalled();
    });
  });

  it("explains that ranking happens in the ordinary flow", async () => {
    mockApis({ allowed: true });
    render(<SupplementaryImportPanel />);
    expect(
      await screen.findByText(/名次由學院於排名階段決定/)
    ).toBeInTheDocument();
  });

  it("keeps the period selector disabled until a scholarship is picked", async () => {
    mockApis({ allowed: true });
    render(<SupplementaryImportPanel />);
    const periodSelect = await screen.findByLabelText("學年學期");
    expect(periodSelect).toBeDisabled();

    await userEvent.selectOptions(
      await screen.findByLabelText("獎學金類型"),
      String(SCHOLARSHIP.id)
    );
    await waitFor(() => expect(periodSelect).toBeEnabled());
  });

  it("blocks upload and explains why when the period is not open", async () => {
    mockApis({ allowed: false });
    render(<SupplementaryImportPanel />);

    await userEvent.selectOptions(
      await screen.findByLabelText("獎學金類型"),
      String(SCHOLARSHIP.id)
    );

    expect(await screen.findByText("尚未開放")).toBeInTheDocument();
    expect(
      screen.getByText("此學年學期尚未開放補充匯入")
    ).toBeInTheDocument();
    expect(document.querySelector('input[type="file"]')).toBeDisabled();
  });

  it("surfaces a failed availability check instead of silently disabling upload", async () => {
    mockApis({ allowed: true });
    jest
      .spyOn(apiClient.college, "getSupplementaryImportAvailability")
      .mockRejectedValue(new Error("使用者未綁定學院，無法使用補充匯入"));

    render(<SupplementaryImportPanel />);
    await userEvent.selectOptions(
      await screen.findByLabelText("獎學金類型"),
      String(SCHOLARSHIP.id)
    );

    // The backend's reason must reach the user — a swallowed failure would leave
    // a disabled drop zone telling them to pick a scholarship they already picked.
    expect(
      await screen.findByText("使用者未綁定學院，無法使用補充匯入")
    ).toBeInTheDocument();
    expect(
      screen.getByText("無法確認開放狀態，請見下方錯誤訊息")
    ).toBeInTheDocument();
    expect(document.querySelector('input[type="file"]')).toBeDisabled();
  });

  it("keeps 下載範本 disabled until a scholarship is chosen", async () => {
    mockApis({ allowed: true });
    render(<SupplementaryImportPanel />);
    expect(await screen.findByRole("button", { name: /下載範本/ })).toBeDisabled();
  });

  it("downloads the template for the selected scholarship", async () => {
    mockApis({ allowed: true });
    render(<SupplementaryImportPanel />);

    await userEvent.selectOptions(
      await screen.findByLabelText("獎學金類型"),
      String(SCHOLARSHIP.id)
    );
    const button = await screen.findByRole("button", { name: /下載範本/ });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);

    await waitFor(() => {
      expect(
        apiClient.college.downloadSupplementaryImportTemplate
      ).toHaveBeenCalledWith(SCHOLARSHIP.code);
    });
  });

  it("offers the template even when the period is not open for import", async () => {
    // The college should be able to prepare the sheet before admin opens the period.
    mockApis({ allowed: false });
    render(<SupplementaryImportPanel />);

    await userEvent.selectOptions(
      await screen.findByLabelText("獎學金類型"),
      String(SCHOLARSHIP.id)
    );
    expect(await screen.findByText("尚未開放")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /下載範本/ })).toBeEnabled();
  });

  it("enables the drop zone once the period is open", async () => {
    mockApis({ allowed: true });
    render(<SupplementaryImportPanel />);

    await userEvent.selectOptions(
      await screen.findByLabelText("獎學金類型"),
      String(SCHOLARSHIP.id)
    );

    expect(await screen.findByText("點擊或拖曳 Excel")).toBeInTheDocument();
    expect(screen.queryByText("尚未開放")).not.toBeInTheDocument();
  });
});
