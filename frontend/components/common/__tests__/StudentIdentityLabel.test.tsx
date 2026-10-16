import { render, screen } from "@testing-library/react";

import { StudentIdentityLabel } from "../StudentIdentityLabel";

const mockUseReferenceData = jest.fn();

jest.mock("@/hooks/use-reference-data", () => ({
  ...jest.requireActual("@/hooks/use-reference-data"),
  useReferenceData: () => mockUseReferenceData(),
}));

// Mirrors the seeded `identities` table (SIS std_identity codes).
const IDENTITIES = [
  { id: 1, name: "一般生" },
  { id: 3, name: "僑生(目前有中華民國國籍生)" },
  { id: 4, name: "外籍生(目前有中華民國國籍生)" },
  { id: 17, name: "陸生" },
];

describe("StudentIdentityLabel", () => {
  beforeEach(() => {
    mockUseReferenceData.mockReturnValue({
      identities: IDENTITIES,
      isLoading: false,
      error: undefined,
    });
  });

  it("labels code 4 as 外籍生, not 陸生", () => {
    render(<StudentIdentityLabel code={4} />);

    expect(
      screen.getByText("外籍生(目前有中華民國國籍生)")
    ).toBeInTheDocument();
    expect(screen.queryByText("陸生")).not.toBeInTheDocument();
  });

  it("labels code 17 as 陸生 and accepts string codes", () => {
    render(<StudentIdentityLabel code="17" />);

    expect(screen.getByText("陸生")).toBeInTheDocument();
  });

  it("shows the unknown fallback for a code missing from the table", () => {
    render(<StudentIdentityLabel code={99} />);

    expect(screen.getByText("未知身份 (99)")).toBeInTheDocument();
  });

  it.each([null, undefined, "", "  "])("shows - for blank code %p", code => {
    render(<StudentIdentityLabel code={code} />);

    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("translates the table name for the English locale", () => {
    render(<StudentIdentityLabel code={17} locale="en" />);

    expect(screen.getByText("Mainland Chinese Student")).toBeInTheDocument();
  });

  it("uses an English unknown fallback for the English locale", () => {
    render(<StudentIdentityLabel code={99} locale="en" />);

    expect(screen.getByText("Unknown identity (99)")).toBeInTheDocument();
  });

  it("shows - while the reference table is still loading", () => {
    mockUseReferenceData.mockReturnValue({ identities: [], isLoading: true });
    render(<StudentIdentityLabel code={4} />);

    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("shows the raw code, not 未知身份, when the reference table failed to load", () => {
    mockUseReferenceData.mockReturnValue({
      identities: [],
      isLoading: false,
      error: new Error("500"),
    });
    render(<StudentIdentityLabel code={4} />);

    const cell = screen.getByText("4");
    expect(cell).toHaveAttribute("title", "身分別資料載入失敗");
    expect(screen.queryByText(/未知身份/)).not.toBeInTheDocument();
  });
});
