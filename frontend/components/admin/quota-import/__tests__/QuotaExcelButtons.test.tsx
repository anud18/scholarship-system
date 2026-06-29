jest.mock("@/hooks/use-reference-data", () => ({
  useReferenceData: () => ({
    academies: [{ id: 1, code: "C", name: "資訊" }],
    subTypeTranslations: { zh: {}, en: {} },
  }),
}));

import { render, screen } from "@testing-library/react";
import { QuotaExcelButtons } from "@/components/admin/quota-import/QuotaExcelButtons";

it("renders the import and template buttons", () => {
  render(<QuotaExcelButtons quotas={{}} subTypes={[{ code: "nstc" }]} onApply={() => {}} />);
  expect(screen.getByText("匯入 Excel")).toBeInTheDocument();
  expect(screen.getByText("下載範本")).toBeInTheDocument();
});
