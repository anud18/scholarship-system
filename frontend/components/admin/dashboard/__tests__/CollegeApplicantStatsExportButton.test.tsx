import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { toast } from "sonner";

import { CollegeApplicantStatsExportButton } from "../CollegeApplicantStatsExportButton";
import { apiClient } from "@/lib/api";
import { triggerBlobDownload } from "@/lib/utils/download";

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
jest.mock("@/lib/utils/download", () => ({ triggerBlobDownload: jest.fn() }));

const BUTTON = { name: /匯出學院申請人數/ };

describe("CollegeApplicantStatsExportButton", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    jest.clearAllMocks();
  });

  it("is disabled until an academic year is selected", () => {
    render(<CollegeApplicantStatsExportButton scholarshipCode="phd" />);
    expect(screen.getByRole("button", BUTTON)).toBeDisabled();
  });

  it("exports the selected scholarship/year/semester and downloads the file", async () => {
    const result = { blob: new Blob(["x"]), filename: "stats.xlsx" };
    const exportSpy = jest
      .spyOn(apiClient.admin, "exportCollegeApplicantStats")
      .mockResolvedValue(result);

    render(
      <CollegeApplicantStatsExportButton
        scholarshipCode="phd"
        academicYear={115}
        semester="first"
      />
    );
    fireEvent.click(screen.getByRole("button", BUTTON));

    await waitFor(() => expect(triggerBlobDownload).toHaveBeenCalledWith(result));
    expect(exportSpy).toHaveBeenCalledWith({
      scholarshipCode: "phd",
      academicYear: 115,
      semester: "first",
    });
  });

  it("shows the backend error message on failure", async () => {
    jest
      .spyOn(apiClient.admin, "exportCollegeApplicantStats")
      .mockRejectedValue(new Error("無權限存取此獎學金類型"));

    render(
      <CollegeApplicantStatsExportButton scholarshipCode="phd" academicYear={115} />
    );
    fireEvent.click(screen.getByRole("button", BUTTON));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("匯出失敗：無權限存取此獎學金類型")
    );
    expect(screen.getByRole("button", BUTTON)).not.toBeDisabled();
  });
});
