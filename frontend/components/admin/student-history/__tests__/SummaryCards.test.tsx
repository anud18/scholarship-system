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
        }}
      />,
    );
    expect(screen.getByText("not-a-number")).toBeInTheDocument();
  });
});
