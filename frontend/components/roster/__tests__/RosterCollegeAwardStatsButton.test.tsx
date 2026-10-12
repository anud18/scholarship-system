import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { toast } from "sonner";

import { RosterCollegeAwardStatsButton } from "../RosterCollegeAwardStatsButton";
import { apiClient } from "@/lib/api";
import { triggerBlobDownload } from "@/lib/utils/download";

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
jest.mock("@/lib/utils/download", () => ({ triggerBlobDownload: jest.fn() }));

const BUTTON = { name: /獲獎人數統計/ };

describe("RosterCollegeAwardStatsButton", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    jest.clearAllMocks();
  });

  it("exports this roster's award stats and downloads the file", async () => {
    const result = { blob: new Blob(["x"]), filename: "stats.xlsx" };
    const exportSpy = jest
      .spyOn(apiClient.paymentRosters, "exportCollegeAwardStats")
      .mockResolvedValue(result);

    render(<RosterCollegeAwardStatsButton rosterId={42} />);
    fireEvent.click(screen.getByRole("button", BUTTON));

    await waitFor(() => expect(triggerBlobDownload).toHaveBeenCalledWith(result));
    expect(exportSpy).toHaveBeenCalledWith(42);
  });

  it("shows the backend error message and re-enables on failure", async () => {
    jest
      .spyOn(apiClient.paymentRosters, "exportCollegeAwardStats")
      .mockRejectedValue(new Error("找不到指定的造冊"));

    render(<RosterCollegeAwardStatsButton rosterId={42} />);
    fireEvent.click(screen.getByRole("button", BUTTON));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("匯出失敗：找不到指定的造冊")
    );
    expect(screen.getByRole("button", BUTTON)).not.toBeDisabled();
  });
});
