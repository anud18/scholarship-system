/**
 * Tests for `FinalizeRankingDialog` — the 確認排名 confirmation that lists the
 * drafts a lock deletes. Confirm must stay disabled whenever a listed sibling
 * is one the backend never deletes (it would answer 409).
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { FinalizeRankingDialog } from "../FinalizeRankingDialog";
import type { RankingScopeFields } from "../ranking-scope";

// Render Radix Dialog inline (no portal / focus-trap issues in jsdom).
jest.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

function renderDialog(siblings: RankingScopeFields[]) {
  const onConfirm = jest.fn();
  render(
    <FinalizeRankingDialog
      locale="zh"
      candidate={{ id: 1, name: "正式版", siblings }}
      isFinalizing={false}
      onCancel={jest.fn()}
      onConfirm={onConfirm}
    />
  );
  return { onConfirm, confirm: screen.getByRole("button", { name: "確認並刪除其他排名" }) };
}

describe("FinalizeRankingDialog", () => {
  it("lists plain drafts and lets the user confirm deleting them", () => {
    const { onConfirm, confirm } = renderDialog([
      { id: 2, ranking_name: "草稿 A" },
      { id: 3, ranking_name: "草稿 B" },
    ]);

    expect(screen.getByText("草稿 A")).toBeInTheDocument();
    expect(screen.getByText("草稿 B")).toBeInTheDocument();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["distributed", { distribution_executed: true }, "（已執行分發或已用於造冊，無法刪除）"],
    ["holding allocation results", { is_settled: true }, "（已執行分發或已用於造冊，無法刪除）"],
    ["used by a roster", { is_roster_referenced: true }, "（已執行分發或已用於造冊，無法刪除）"],
    ["locked", { is_finalized: true }, "（已鎖定，無法刪除）"],
  ])("disables confirm while a listed sibling is %s", (_label, overrides, note) => {
    const { onConfirm, confirm } = renderDialog([
      { id: 2, ranking_name: "草稿 A" },
      { id: 3, ranking_name: "受保護", ...overrides },
    ]);

    expect(screen.getByText(note, { exact: false })).toBeInTheDocument();
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
