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

  it("shows - for a blank code", () => {
    render(<StudentIdentityLabel code={null} />);

    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("shows - while the reference table is still loading", () => {
    mockUseReferenceData.mockReturnValue({ identities: [], isLoading: true });
    render(<StudentIdentityLabel code={4} />);

    expect(screen.getByText("-")).toBeInTheDocument();
  });
});
