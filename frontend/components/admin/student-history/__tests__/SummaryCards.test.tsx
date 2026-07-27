import { render, screen } from "@testing-library/react";
import { SummaryCards } from "../SummaryCards";

describe("SummaryCards (G28/#990)", () => {
  it("renders count, TWD-formatted total, and type count", () => {
    render(
      <SummaryCards
        summary={{
          total_records: 12,
          total_amount: "240000",
          scholarship_type_count: 2,
          snapshot_name: "王小明",
          total_received_months: 26,
        }}
      />,
    );
    expect(screen.getByText("總筆數")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    // 貨幣符號 (NT$ vs $) 依 ICU 而異 — 斷言數值部分即可
    expect(screen.getByText(/240,000/)).toBeInTheDocument();
    expect(screen.getByText("獎學金類型數")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("passes through unparseable amounts verbatim instead of NaN", () => {
    render(
      <SummaryCards
        summary={{
          total_records: 0,
          total_amount: "not-a-number",
          scholarship_type_count: 0,
          snapshot_name: null,
          total_received_months: 0,
        }}
      />,
    );
    expect(screen.getByText("not-a-number")).toBeInTheDocument();
  });

  it("shows 總領月份數 with its cross-scholarship caveat", () => {
    render(
      <SummaryCards
        summary={{
          total_records: 1,
          total_amount: "40000",
          scholarship_type_count: 1,
          snapshot_name: null,
          total_received_months: 25,
        }}
      />,
    );
    expect(screen.getByText("總領月份數")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(
      screen.getByText("各獎學金合計，含匯入與系統計算"),
    ).toBeInTheDocument();
  });

  it("renders 0 rather than blank when the field is absent from an older response", () => {
    const stale = {
      total_records: 0,
      total_amount: "0",
      scholarship_type_count: 0,
      snapshot_name: null,
    } as unknown as Parameters<typeof SummaryCards>[0]["summary"];

    render(<SummaryCards summary={stale} />);

    expect(screen.getByText("總領月份數")).toBeInTheDocument();
    // Three zeros: 總筆數, 獎學金類型數, 總領月份數.
    expect(screen.getAllByText("0")).toHaveLength(3);
  });
});
