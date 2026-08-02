import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { HistoryVisibilityCard } from "../HistoryVisibilityCard";
import { useStudentHistoryVisibility } from "@/hooks/use-student-history-visibility";
import { apiClient } from "@/lib/api";

jest.mock("@/hooks/use-student-history-visibility");
jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const mockUseVisibility = useStudentHistoryVisibility as jest.MockedFunction<
  typeof useStudentHistoryVisibility
>;

const mutate = jest.fn();

function mockVisibility(studentEnabled: boolean, collegeEnabled: boolean) {
  mockUseVisibility.mockReturnValue({
    visibility: {
      student_enabled: studentEnabled,
      college_enabled: collegeEnabled,
    },
    isLoaded: true,
    isLoading: false,
    error: undefined,
    mutate,
  } as unknown as ReturnType<typeof useStudentHistoryVisibility>);
}

describe("HistoryVisibilityCard", () => {
  let updateVisibility: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    updateVisibility = jest
      .spyOn(apiClient.studentHistory, "updateVisibility")
      .mockResolvedValue({
        success: true,
        message: "ok",
        data: { student_enabled: true, college_enabled: false },
      });
  });

  afterEach(() => {
    updateVisibility.mockRestore();
  });

  it("reflects the stored state of both switches", () => {
    mockVisibility(true, false);
    render(<HistoryVisibilityCard />);

    expect(screen.getByLabelText("開放學生查詢")).toBeChecked();
    expect(screen.getByLabelText("開放學院查詢")).not.toBeChecked();
  });

  it("sends only the toggled audience so the other switch is untouched", async () => {
    mockVisibility(true, true);
    render(<HistoryVisibilityCard />);

    await userEvent.click(screen.getByLabelText("開放學院查詢"));

    await waitFor(() =>
      expect(updateVisibility).toHaveBeenCalledWith({ college_enabled: false }),
    );
    // The server response (both switches) is what refreshes the cache.
    expect(mutate).toHaveBeenCalledWith(
      { student_enabled: true, college_enabled: false },
      { revalidate: false },
    );
  });
});
