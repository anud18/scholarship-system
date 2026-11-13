/**
 * Tests for `CollegeRankingOverviewPanel` — admin 學院排名繳交 overview.
 *
 * Spies on the REAL apiClient singleton (a factory jest.mock of "@/lib/api"
 * does not intercept the component's import under this repo's ESM jest setup).
 */
import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";

import { buildPeriodOptions, CollegeRankingOverviewPanel } from "../CollegeRankingOverviewPanel";
import { apiClient } from "@/lib/api";
import type { CollegeRankingOverview } from "@/lib/api/modules/admin";
import { triggerBlobDownload } from "@/lib/utils/download";

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
jest.mock("@/lib/utils/download", () => ({ triggerBlobDownload: jest.fn() }));

const CONFIGURATIONS = [
  { scholarship_type_code: "phd", scholarship_type_name: "博士生獎學金", academic_year: 115, semester: null },
  { scholarship_type_code: "phd", scholarship_type_name: "博士生獎學金", academic_year: 115, semester: "yearly" },
  { scholarship_type_code: "direct_phd", scholarship_type_name: "逕博獎學金", academic_year: 114, semester: "first" },
];

const OVERVIEW: CollegeRankingOverview = {
  scholarship: { id: 1, code: "phd", name: "博士生獎學金" },
  academic_year: 115,
  semester: null,
  summary: { not_created: 1, draft: 0, draft_imported: 1, finalized: 1, total: 3 },
  colleges: [
    {
      college_code: "A",
      college_name: "人社院",
      applicant_count: 4,
      status: "not_created",
      last_import_at: null,
      last_import_by: null,
      rankings: [],
    },
    {
      college_code: "C",
      college_name: "資訊學院",
      applicant_count: 7,
      status: "draft_imported",
      last_import_at: "2026-11-03T08:00:00+00:00",
      last_import_by: "資訊承辦",
      rankings: [
        {
          id: 11,
          ranking_name: "草稿一",
          sub_type_code: "nstc",
          is_finalized: false,
          distribution_executed: false,
          total_applications: 7,
          created_at: "2026-11-01T08:00:00+00:00",
          created_by: "資訊承辦",
          finalized_at: null,
          finalized_by: null,
          last_import_at: null,
          last_import_by: null,
        },
        {
          id: 12,
          ranking_name: "草稿二",
          sub_type_code: "nstc",
          is_finalized: false,
          distribution_executed: false,
          total_applications: 7,
          created_at: "2026-11-02T08:00:00+00:00",
          created_by: "資訊承辦",
          finalized_at: null,
          finalized_by: null,
          last_import_at: "2026-11-03T08:00:00+00:00",
          last_import_by: "資訊承辦",
        },
      ],
    },
    {
      college_code: "E",
      college_name: "電機學院",
      applicant_count: 9,
      status: "finalized",
      last_import_at: null,
      last_import_by: null,
      rankings: [
        {
          id: 21,
          ranking_name: "電機排名",
          sub_type_code: "nstc",
          is_finalized: true,
          distribution_executed: false,
          total_applications: 9,
          created_at: "2026-11-01T08:00:00+00:00",
          created_by: "電機承辦",
          finalized_at: "2026-11-05T08:00:00+00:00",
          finalized_by: "電機承辦",
          last_import_at: null,
          last_import_by: null,
        },
      ],
    },
  ],
};

function mockApi(overview: CollegeRankingOverview = OVERVIEW) {
  jest
    .spyOn(apiClient.admin, "getScholarshipConfigurations")
    .mockResolvedValue({ success: true, message: "", data: CONFIGURATIONS } as any);
  return jest
    .spyOn(apiClient.admin, "getCollegeRankingOverview")
    .mockResolvedValue({ success: true, message: "", data: overview } as any);
}

function rowOf(collegeName: string): HTMLElement {
  return screen.getByText(collegeName).closest("tr") as HTMLElement;
}

describe("buildPeriodOptions", () => {
  it("collapses configurations of one period and treats yearly as no semester", () => {
    const options = buildPeriodOptions(CONFIGURATIONS);

    expect(options.map(option => option.label)).toEqual([
      "115 學年度｜博士生獎學金",
      "114 學年度 第一學期｜逕博獎學金",
    ]);
    expect(options[0].semester).toBeUndefined();
    expect(options[1].semester).toBe("first");
  });
});

describe("CollegeRankingOverviewPanel", () => {
  beforeEach(() => {
    jest.restoreAllMocks();
    jest.clearAllMocks();
  });

  it("loads the newest period and shows each college's status", async () => {
    const overviewSpy = mockApi();

    render(<CollegeRankingOverviewPanel />);

    await waitFor(() => expect(screen.getByText("人社院")).toBeInTheDocument());
    expect(overviewSpy).toHaveBeenCalledWith({
      scholarshipCode: "phd",
      academicYear: 115,
      semester: undefined,
    });
    expect(within(rowOf("人社院")).getByText("尚未建立排名")).toBeInTheDocument();
    expect(within(rowOf("資訊學院")).getByText("草稿已匯入")).toBeInTheDocument();
    expect(within(rowOf("資訊學院")).getAllByText("資訊承辦").length).toBeGreaterThan(0);
    expect(within(rowOf("電機學院")).getAllByText("已確認").length).toBeGreaterThan(0);
    expect(screen.getByText("共 3 個學院")).toBeInTheDocument();
    // A college without a ranking has nothing to export.
    expect(within(rowOf("人社院")).queryByRole("button")).not.toBeInTheDocument();
  });

  it("exports each draft of a college separately, as Excel or PDF", async () => {
    mockApi();
    const result = { blob: new Blob(["x"]), filename: "ranking.pdf" };
    const exportSpy = jest.spyOn(apiClient.college, "exportRankingExcel").mockResolvedValue(result);

    render(<CollegeRankingOverviewPanel />);
    await waitFor(() => expect(screen.getByText("草稿二")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "匯出 草稿二 PDF" }));
    await waitFor(() => expect(triggerBlobDownload).toHaveBeenCalledWith(result));
    expect(exportSpy).toHaveBeenCalledWith(12, "pdf");

    fireEvent.click(screen.getByRole("button", { name: "匯出 草稿一 Excel" }));
    await waitFor(() => expect(exportSpy).toHaveBeenCalledWith(11, "xlsx"));
  });

  it("shows the backend error when an export fails", async () => {
    mockApi();
    jest.spyOn(apiClient.college, "exportRankingExcel").mockRejectedValue(new Error("無權限存取此獎學金類型"));

    render(<CollegeRankingOverviewPanel />);
    await waitFor(() => expect(screen.getByText("電機排名")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "匯出 電機排名 Excel" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("匯出失敗：無權限存取此獎學金類型"));
    expect(triggerBlobDownload).not.toHaveBeenCalled();
  });

  it("shows the load error instead of a stale table", async () => {
    jest
      .spyOn(apiClient.admin, "getScholarshipConfigurations")
      .mockResolvedValue({ success: true, message: "", data: CONFIGURATIONS } as any);
    jest
      .spyOn(apiClient.admin, "getCollegeRankingOverview")
      .mockResolvedValue({ success: false, message: "找不到此獎學金類型" } as any);

    render(<CollegeRankingOverviewPanel />);

    await waitFor(() => expect(screen.getByText("找不到此獎學金類型")).toBeInTheDocument());
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
