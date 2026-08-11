/**
 * Pins the 重新生成 action on the 造冊列表 row.
 *
 * The gating is subtle and was wrong once: the cycle-status endpoint collapses
 * BOTH `COMPLETED` and `LOCKED` rosters into `period.status = "completed"`, and
 * only `period.roster_status` carries the real state. A gate written against
 * `period.status` therefore offers 重新生成 on a locked roster, which the backend
 * refuses with 400「請先解鎖」.
 */

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { RosterListTable } from "../roster/RosterListTable";
import { apiClient } from "@/lib/api";

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const basePeriod = {
  label: "115",
  status: "completed" as const,
  roster_id: 42,
  roster_code: "ROSTER-115-nstc",
  roster_status: "completed",
  sub_type: "nstc",
  allocation_year: 115,
  qualified_count: 3,
};

function renderTable(
  overrides: Partial<typeof basePeriod> = {},
  onRosterGenerated = jest.fn()
) {
  render(
    <RosterListTable
      periods={[{ ...basePeriod, ...overrides }]}
      configId={1}
      rosterCycle="yearly"
      onRosterGenerated={onRosterGenerated}
    />
  );
  return { onRosterGenerated };
}

describe("RosterListTable 重新生成", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    jest.clearAllMocks();
  });

  it("offers 重新生成 on a completed roster", () => {
    renderTable();
    expect(screen.getByRole("button", { name: /重新生成/ })).toBeInTheDocument();
  });

  it("hides 重新生成 on a LOCKED roster even though period.status says completed", () => {
    // This exact shape is what /cycle-status returns for a locked roster.
    renderTable({ status: "completed", roster_status: "locked" });
    expect(screen.queryByRole("button", { name: /重新生成/ })).toBeNull();
    expect(screen.getByText("已鎖定")).toBeInTheDocument();
  });

  it("regenerates by roster_id and refreshes the parent after confirmation", async () => {
    const spy = jest
      .spyOn(apiClient.paymentRosters, "regenerateRoster")
      .mockResolvedValue({
        success: true,
        message: "已重新生成造冊：3 筆明細",
        data: undefined,
      } as never);
    jest.spyOn(window, "confirm").mockReturnValue(true);

    const { onRosterGenerated } = renderTable();
    fireEvent.click(screen.getByRole("button", { name: /重新生成/ }));

    await waitFor(() => expect(spy).toHaveBeenCalledWith(42));
    await waitFor(() => expect(onRosterGenerated).toHaveBeenCalled());
  });

  it("does not call the API when the admin cancels the confirmation", () => {
    const spy = jest.spyOn(apiClient.paymentRosters, "regenerateRoster");
    jest.spyOn(window, "confirm").mockReturnValue(false);

    renderTable();
    fireEvent.click(screen.getByRole("button", { name: /重新生成/ }));

    expect(spy).not.toHaveBeenCalled();
  });
});
