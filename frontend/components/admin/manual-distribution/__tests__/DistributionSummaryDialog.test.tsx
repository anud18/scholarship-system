import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DistributionSummaryDialog } from "../DistributionSummaryDialog";
import type { DistributionSummaryResult } from "@/lib/api/modules/manual-distribution";

// Radix's DropdownMenu drives its open state from Pointer Events, which jsdom
// does not implement — without these stubs the trigger never opens and every
// export assertion below fails for an environment reason, not a code one.
beforeAll(() => {
  Object.defineProperty(Element.prototype, "hasPointerCapture", {
    value: () => false,
    writable: true,
  });
  Object.defineProperty(Element.prototype, "releasePointerCapture", {
    value: () => {},
    writable: true,
  });
  Object.defineProperty(Element.prototype, "setPointerCapture", {
    value: () => {},
    writable: true,
  });
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    value: () => {},
    writable: true,
  });
});

/** Open the 匯出 dropdown and click one of its items. */
async function clickExportItem(label: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /匯出/ }));
  await user.click(await screen.findByText(label));
}

const mockExport = jest.fn();
const mockTriggerBlobDownload = jest.fn();
const mockToast = { success: jest.fn(), error: jest.fn() };

jest.mock("@/lib/api/modules/manual-distribution", () => ({
  exportDistributionSummary: (...args: unknown[]) => mockExport(...args),
  resolveCollegeName: (
    names: Map<string, string>,
    code: string,
    fallback?: string
  ) => (code ? (names.get(code) ?? code) : fallback || "未知"),
}));

jest.mock("@/lib/utils/download", () => ({
  triggerBlobDownload: (...args: unknown[]) => mockTriggerBlobDownload(...args),
}));

jest.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => mockToast.success(...args),
    error: (...args: unknown[]) => mockToast.error(...args),
  },
}));

const summary = (): DistributionSummaryResult => ({
  total_allocated: 2,
  groups: [
    {
      sub_type: "nstc",
      allocation_config_id: 42,
      allocation_year: 114,
      count: 2,
      students: [
        {
          ranking_item_id: 2,
          application_id: 20,
          student_name: "李二",
          student_id: "312345602",
          college_code: "I",
          college_name: "工學院",
          department_name: "土木工程學系",
          rank_position: 2,
        },
        {
          ranking_item_id: 1,
          application_id: 10,
          student_name: "王一",
          student_id: "312345601",
          college_code: "I",
          college_name: "工學院",
          department_name: "土木工程學系",
          rank_position: 1,
        },
      ],
    },
  ],
});

const defaults = {
  collegeNames: new Map([["I", "工學院"]]),
  getSubTypeLabel: (code: string) => (code === "nstc" ? "國科會" : code),
  scholarshipTypeId: 7,
  academicYear: 114,
  semester: "yearly",
  onClose: jest.fn(),
};

beforeEach(() => {
  jest.clearAllMocks();
  mockExport.mockResolvedValue({ blob: new Blob(["x"]), filename: "分發名單.xlsx" });
});

describe("DistributionSummaryDialog", () => {
  it("renders each group's students sorted by rank without mutating the prop array", () => {
    const data = summary();
    const original = data.groups[0].students;
    render(<DistributionSummaryDialog {...defaults} summary={data} isLoading={false} />);

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(rows[0]).toHaveTextContent("王一");
    expect(rows[1]).toHaveTextContent("李二");
    // The panel reuses this array; sorting it in place would reorder its state.
    expect(original.map((s) => s.student_name)).toEqual(["李二", "王一"]);
  });

  it("shows the group heading with label, raw code and 年度配額", () => {
    render(<DistributionSummaryDialog {...defaults} summary={summary()} isLoading={false} />);
    expect(screen.getByText("國科會")).toBeInTheDocument();
    expect(screen.getByText("(nstc)")).toBeInTheDocument();
    expect(screen.getByText("114 年度配額")).toBeInTheDocument();
  });

  it("exports xlsx with the current selection and triggers the download", async () => {
    render(<DistributionSummaryDialog {...defaults} summary={summary()} isLoading={false} />);
    await clickExportItem("匯出 Excel");

    await waitFor(() => expect(mockExport).toHaveBeenCalledTimes(1));
    expect(mockExport).toHaveBeenCalledWith({
      scholarshipTypeId: 7,
      academicYear: 114,
      semester: "yearly",
      format: "xlsx",
    });
    expect(mockTriggerBlobDownload).toHaveBeenCalledWith({
      blob: expect.any(Blob),
      filename: "分發名單.xlsx",
    });
    expect(mockToast.success).toHaveBeenCalledWith("匯出成功");
  });

  it("passes format=pdf through for the PDF item", async () => {
    render(<DistributionSummaryDialog {...defaults} summary={summary()} isLoading={false} />);
    await clickExportItem("匯出 PDF");

    await waitFor(() => expect(mockExport).toHaveBeenCalledTimes(1));
    expect(mockExport.mock.calls[0][0].format).toBe("pdf");
  });

  it("surfaces the backend message when the export fails", async () => {
    mockExport.mockRejectedValue(new Error("尚未完成分發，無法匯出"));
    render(<DistributionSummaryDialog {...defaults} summary={summary()} isLoading={false} />);
    await clickExportItem("匯出 Excel");

    await waitFor(() =>
      expect(mockToast.error).toHaveBeenCalledWith("尚未完成分發，無法匯出")
    );
    expect(mockTriggerBlobDownload).not.toHaveBeenCalled();
  });

  it("disables 匯出 when there is nothing to export", () => {
    render(
      <DistributionSummaryDialog
        {...defaults}
        summary={{ groups: [], total_allocated: 0 }}
        isLoading={false}
      />
    );
    expect(screen.getByRole("button", { name: /匯出/ })).toBeDisabled();
    expect(screen.getByText("尚未完成分發，或無已分配的學生")).toBeInTheDocument();
  });

  it("tells the admin to pick a year instead of silently no-opping", async () => {
    render(
      <DistributionSummaryDialog
        {...defaults}
        academicYear={undefined}
        summary={summary()}
        isLoading={false}
      />
    );
    await clickExportItem("匯出 Excel");

    await waitFor(() =>
      expect(mockToast.error).toHaveBeenCalledWith("請先選擇學年度與學期")
    );
    expect(mockExport).not.toHaveBeenCalled();
  });

  it("renders a red N instead of the rank for a college-rejected row", () => {
    const data = summary();
    data.groups[0].students[1].college_rejected = true;
    render(<DistributionSummaryDialog {...defaults} summary={data} isLoading={false} />);
    expect(screen.getByText("N")).toBeInTheDocument();
  });

  it("closes via the footer button", () => {
    const onClose = jest.fn();
    render(
      <DistributionSummaryDialog {...defaults} onClose={onClose} summary={summary()} isLoading={false} />
    );
    fireEvent.click(screen.getByRole("button", { name: "關閉" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
