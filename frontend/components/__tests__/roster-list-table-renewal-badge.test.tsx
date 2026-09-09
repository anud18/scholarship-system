/**
 * 造冊列表 marks rosters that carry 續領 rows.
 *
 * A 115 renewal of a 114 award consumes the 114 slot (allocation_year 114)
 * but is paid in the 115 period, so its roster row shows label 115 with the
 * 114 配額年度 — the badge is what tells the admin at a glance that this is
 * the renewal roster rather than a 補發.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { RosterListTable } from "../roster/RosterListTable";

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const basePeriod = {
  label: "115",
  status: "completed" as const,
  roster_id: 42,
  roster_code: "ROSTER-115-nstc-phd_114-phd_115",
  roster_status: "completed",
  sub_type: "nstc",
  allocation_year: 114,
  project_number: "114R000001",
  qualified_count: 3,
  period_start_date: "2026-09-01T00:00:00",
  period_end_date: "2027-08-31T00:00:00",
};

function renderTable(
  overrides: Partial<typeof basePeriod & { renewal_count: number }> = {}
) {
  render(
    <RosterListTable
      periods={[{ ...basePeriod, ...overrides }]}
      configId={1}
      rosterCycle="yearly"
    />
  );
}

describe("RosterListTable 續領 badge", () => {
  it("shows the included-renewal count next to the sub-type", () => {
    renderTable({ renewal_count: 2 });
    expect(screen.getByText("續領 2 人")).toBeInTheDocument();
    expect(screen.getByText("nstc")).toBeInTheDocument();
    expect(screen.getByText("114")).toBeInTheDocument();
    expect(screen.getByText("114R000001")).toBeInTheDocument();
  });

  it("renders the 造冊期間 for a distribution-generated roster", () => {
    renderTable({ renewal_count: 1 });
    expect(screen.getByText(/2026\/09\/01 - 2027\/08\/31/)).toBeInTheDocument();
  });

  it("omits the badge when the roster has no renewals or the field is absent", () => {
    renderTable({ renewal_count: 0 });
    expect(screen.queryByText(/續領 \d+ 人/)).toBeNull();
  });

  it("shows 尚無可造冊名單 instead of 立即產生 when nothing is eligible yet", () => {
    render(
      <RosterListTable
        periods={[
          {
            label: "115-09",
            status: "waiting",
            academic_year: 115,
            year_offset: 1,
            segment: "續領",
            estimated_count: 0,
          },
          {
            label: "115-10",
            status: "waiting",
            academic_year: 115,
            year_offset: 1,
            segment: "續領",
            estimated_count: 3,
          },
        ]}
        configId={1}
        rosterCycle="monthly"
      />
    );
    expect(screen.getByText("尚無可造冊名單")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /立即產生/ })).toHaveLength(1);
    expect(screen.getByText("第二年 續領（115 學年度）")).toBeInTheDocument();
  });
});
