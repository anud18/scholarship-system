import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ReceivedMonthsCard } from "../ReceivedMonthsCard";
import type { ReceivedMonthsBreakdown } from "@/lib/api/modules/student-history";

const IMPORTED: ReceivedMonthsBreakdown = {
  scholarship_type_id: 1,
  scholarship_name: "國科會博士生獎學金",
  total_months: 26,
  imported_months: 24,
  system_months: 2,
  award_start_month: "113年9月",
  award_current_month: "115年8月",
  raw_row: {
    學號: "310460031",
    領獎起始月份: "113年9月",
    目前領獎月份: "115年8月",
    "休學/退學/畢業": "115年9月休學",
  },
  file_name: "nstc_received.xlsx",
  imported_at: "2026-07-28T02:00:00+00:00",
};

const SYSTEM_ONLY: ReceivedMonthsBreakdown = {
  scholarship_type_id: 2,
  scholarship_name: "教育部博士生獎學金",
  total_months: 6,
  imported_months: 0,
  system_months: 6,
  award_start_month: null,
  award_current_month: null,
  raw_row: null,
  file_name: null,
  imported_at: null,
};

describe("ReceivedMonthsCard", () => {
  it("renders nothing when there is no 已領月份數 at all", () => {
    const { container } = render(<ReceivedMonthsCard breakdowns={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the total and the 匯入 + 系統 split", () => {
    render(<ReceivedMonthsCard breakdowns={[IMPORTED]} />);

    expect(screen.getByText("國科會博士生獎學金")).toBeInTheDocument();
    expect(screen.getByText("26")).toBeInTheDocument();
    // The split must stay visible so an admin can see where the number came from.
    expect(
      screen.getByText(/匯入 24 \(113年9月–115年8月\) · 系統 2/),
    ).toBeInTheDocument();
  });

  it("marks a breakdown that includes an imported baseline", () => {
    render(<ReceivedMonthsCard breakdowns={[IMPORTED, SYSTEM_ONLY]} />);
    expect(screen.getAllByText("含匯入")).toHaveLength(1);
  });

  it("offers 檔案明細 only when a source row was stored", () => {
    render(<ReceivedMonthsCard breakdowns={[IMPORTED, SYSTEM_ONLY]} />);
    expect(screen.getAllByRole("button", { name: /檔案明細/ })).toHaveLength(1);
  });

  it("reveals every column of the original file on expand", async () => {
    const user = userEvent.setup();
    render(<ReceivedMonthsCard breakdowns={[IMPORTED]} />);

    expect(screen.queryByText("休學/退學/畢業")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /檔案明細/ }));

    expect(screen.getByText("休學/退學/畢業")).toBeInTheDocument();
    expect(screen.getByText("115年9月休學")).toBeInTheDocument();
    expect(screen.getByText("310460031")).toBeInTheDocument();
    expect(screen.getByText("nstc_received.xlsx")).toBeInTheDocument();
  });

  it("collapses again on a second click", async () => {
    const user = userEvent.setup();
    render(<ReceivedMonthsCard breakdowns={[IMPORTED]} />);
    const toggle = screen.getByRole("button", { name: /檔案明細/ });

    await user.click(toggle);
    expect(screen.getByText("休學/退學/畢業")).toBeInTheDocument();

    await user.click(toggle);
    expect(screen.queryByText("休學/退學/畢業")).not.toBeInTheDocument();
  });

  it("omits the 匯入 clause for a system-only scholarship", () => {
    render(<ReceivedMonthsCard breakdowns={[SYSTEM_ONLY]} />);
    expect(screen.getByText("系統 6")).toBeInTheDocument();
    expect(screen.queryByText(/匯入/)).not.toBeInTheDocument();
  });
});
