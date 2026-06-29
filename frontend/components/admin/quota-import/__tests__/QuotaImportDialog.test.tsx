import { render, screen } from "@testing-library/react";
import { QuotaImportDialog } from "@/components/admin/quota-import/QuotaImportDialog";

const colleges = [{ code: "C", name: "資訊" }];
const subs = [{ code: "nstc" }];

it("disables 確認套用 when there are errors", () => {
  render(
    <QuotaImportDialog
      open
      onOpenChange={() => {}}
      result={{ quotas: { nstc: { C: 0 } }, errors: [{ kind: "cell", severity: "error", message: "bad" }], warnings: [] }}
      currentQuotas={{}}
      knownColleges={colleges}
      knownSubTypes={subs}
      onConfirm={() => {}}
    />,
  );
  expect(screen.getByText("確認套用").closest("button")).toBeDisabled();
});

it("enables 確認套用 with no errors and renders a diff cell", () => {
  render(
    <QuotaImportDialog
      open
      onOpenChange={() => {}}
      result={{ quotas: { nstc: { C: 5 } }, errors: [], warnings: [] }}
      currentQuotas={{ nstc: { C: 2 } }}
      knownColleges={colleges}
      knownSubTypes={subs}
      onConfirm={() => {}}
    />,
  );
  expect(screen.getByText("確認套用").closest("button")).not.toBeDisabled();
  expect(screen.getByText("2→5")).toBeInTheDocument();
});
