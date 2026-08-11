import React from "react";
import { render, screen, waitFor } from "@testing-library/react";

import { TotalReceivedMonthsCard } from "../TotalReceivedMonthsCard";
import { useStudentHistoryVisibility } from "@/hooks/use-student-history-visibility";
import { apiClient } from "@/lib/api";

jest.mock("@/hooks/use-student-history-visibility");

const mockUseVisibility = useStudentHistoryVisibility as jest.MockedFunction<
  typeof useStudentHistoryVisibility
>;

function mockVisibility(studentEnabled: boolean) {
  mockUseVisibility.mockReturnValue({
    visibility: { student_enabled: studentEnabled, college_enabled: true },
    isLoaded: true,
    isLoading: false,
    error: undefined,
    mutate: jest.fn(),
  } as unknown as ReturnType<typeof useStudentHistoryVisibility>);
}

describe("TotalReceivedMonthsCard", () => {
  let getMyMonths: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    // spyOn the real client: a jest.mock factory for "@/lib/api" does not
    // intercept the module's own top-level import graph in this setup.
    getMyMonths = jest
      .spyOn(apiClient.studentHistory, "getMyMonths")
      .mockResolvedValue({
        success: true,
        message: "ok",
        data: { student_number: "stuphd001", total_received_months: 7 },
      });
  });

  afterEach(() => {
    getMyMonths.mockRestore();
  });

  it("renders the total once the admin has opened 學生查詢", async () => {
    mockVisibility(true);
    render(<TotalReceivedMonthsCard />);

    expect(
      await screen.findByTestId("total-received-months-card"),
    ).toHaveTextContent("7");
    expect(getMyMonths).toHaveBeenCalledTimes(1);
  });

  it("renders nothing and skips the request when 學生查詢 is closed", async () => {
    mockVisibility(false);
    render(<TotalReceivedMonthsCard />);

    await waitFor(() => expect(getMyMonths).not.toHaveBeenCalled());
    expect(
      screen.queryByTestId("total-received-months-card"),
    ).not.toBeInTheDocument();
  });
});
