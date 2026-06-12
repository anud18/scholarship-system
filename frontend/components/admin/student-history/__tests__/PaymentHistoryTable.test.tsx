import { render, screen } from "@testing-library/react";
import { PaymentHistoryTable } from "../PaymentHistoryTable";
import type { PaymentRecord } from "@/lib/api/modules/student-history";

function record(overrides: Partial<PaymentRecord> = {}): PaymentRecord {
  return {
    roster_id: 1,
    roster_code: "ROSTER-114-10",
    period_label: "114-10",
    academic_year: 114,
    roster_cycle: "monthly",
    scholarship_name: "博士生獎學金",
    scholarship_amount: "20000",
    scholarship_subtype: "nstc",
    allocation_year: 114,
    locked_at: "2026-05-01T00:00:00Z",
    quota_allocation_status: null,
    revoked_at: null,
    revoke_reason: null,
    suspended_at: null,
    suspend_reason: null,
    ...overrides,
  };
}

describe("PaymentHistoryTable (G28/#990)", () => {
  it("renders the empty state when there are no records", () => {
    render(<PaymentHistoryTable records={[]} />);
    expect(screen.getByText("尚無領取記錄")).toBeInTheDocument();
  });

  it("renders rows with formatted amounts and the record count", () => {
    render(
      <PaymentHistoryTable
        records={[record(), record({ period_label: "114-09", scholarship_amount: "5000" })]}
      />,
    );
    expect(screen.getByText("領取明細 (2 筆)")).toBeInTheDocument();
    expect(screen.getByText("114-10")).toBeInTheDocument();
    expect(screen.getByText(/20,000/)).toBeInTheDocument();
    expect(screen.getByText(/5,000/)).toBeInTheDocument();
  });

  it("shows the 已撤銷 badge with the reason tooltip for revoked-after-lock payments (G25)", () => {
    render(
      <PaymentHistoryTable
        records={[
          record({
            quota_allocation_status: "revoked",
            revoked_at: "2026-06-01T00:00:00Z",
            revoke_reason: "違反要點第七條",
          }),
        ]}
      />,
    );
    const badge = screen.getByText("已撤銷");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("title", "違反要點第七條");
  });

  it("shows the 已停發 badge for suspended payments (G25)", () => {
    render(
      <PaymentHistoryTable
        records={[
          record({
            quota_allocation_status: "suspended",
            suspended_at: "2026-06-01T00:00:00Z",
            suspend_reason: "休學",
          }),
        ]}
      />,
    );
    expect(screen.getByText("已停發")).toHaveAttribute("title", "休學");
  });

  it("shows NO status badge for normal payments", () => {
    render(<PaymentHistoryTable records={[record()]} />);
    expect(screen.queryByText("已撤銷")).not.toBeInTheDocument();
    expect(screen.queryByText("已停發")).not.toBeInTheDocument();
  });
});
