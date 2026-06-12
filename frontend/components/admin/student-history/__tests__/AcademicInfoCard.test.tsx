import { render, screen } from "@testing-library/react";
import { AcademicInfoCard } from "../AcademicInfoCard";

// AcademicInfoCard resolves degree/status/academy labels via the
// reference-data hook; stub it so the test exercises the component's own
// rendering logic, not the network.
jest.mock("@/hooks/use-reference-data", () => ({
  useReferenceData: () => ({ degrees: [], studyingStatuses: [], academies: [] }),
  getDegreeName: () => "博士",
  getStudyingStatusName: () => "在學",
  getAcademyName: () => "電機學院",
}));

describe("AcademicInfoCard (G28/#990)", () => {
  it("renders the SIS-degraded state with the roster snapshot name", () => {
    render(
      <AcademicInfoCard
        academicInfo={{ available: false, error: "SIS timeout", basic_info: null }}
        snapshotName="王小明"
      />,
    );
    expect(screen.getByText("無即時學籍資料")).toBeInTheDocument();
    expect(screen.getByText("SIS timeout")).toBeInTheDocument();
    expect(screen.getByText("王小明")).toBeInTheDocument();
  });

  it("renders the degraded state without a snapshot name gracefully", () => {
    render(
      <AcademicInfoCard
        academicInfo={{ available: false, error: null, basic_info: null }}
        snapshotName={null}
      />,
    );
    expect(screen.getByText("無即時學籍資料")).toBeInTheDocument();
    expect(screen.queryByText("造冊快照姓名:")).not.toBeInTheDocument();
  });

  it("renders SIS basic info when available", () => {
    render(
      <AcademicInfoCard
        academicInfo={{
          available: true,
          error: null,
          basic_info: {
            std_cname: "王小明",
            std_ename: "WANG,HSIAO-MING",
            std_degree: "1",
            std_studingstatus: "1",
            std_academyno: "E",
            std_aca_cname: "電機學院",
            std_depname: "電機工程學系博士班",
            std_depno: "3551",
            com_email: "wang@nycu.edu.tw",
          },
        }}
        snapshotName={null}
      />,
    );
    expect(screen.getByText("學籍資料")).toBeInTheDocument();
    expect(screen.getByText("王小明")).toBeInTheDocument();
    expect(screen.getByText("電機工程學系博士班")).toBeInTheDocument();
  });

  it("renders nothing when available but basic_info missing", () => {
    const { container } = render(
      <AcademicInfoCard
        academicInfo={{ available: true, error: null, basic_info: null }}
        snapshotName={null}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
