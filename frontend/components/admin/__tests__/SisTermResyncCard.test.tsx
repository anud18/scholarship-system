/**
 * Tests for `SisTermResyncCard` — admin 學籍學期資料 status + 重新同步 action.
 *
 * Spies on the REAL apiClient singleton (a factory jest.mock of "@/lib/api"
 * does not intercept the component's import under this repo's ESM jest setup).
 */
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SisTermResyncCard } from "../SisTermResyncCard";
import { apiClient } from "@/lib/api";

afterEach(() => {
  jest.restoreAllMocks();
});

describe("SisTermResyncCard", () => {
  it("hides the resync action when term data is complete", () => {
    render(
      <SisTermResyncCard
        applicationId={1}
        studentData={{ _term_data_status: "success" }}
        locale="zh"
        onResynced={jest.fn()}
      />
    );

    expect(screen.getByText("完整")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /重新同步/ })).not.toBeInTheDocument();
  });

  it("resyncs a failed snapshot and asks the parent to reload", async () => {
    const resync = jest
      .spyOn(apiClient.admin, "resyncSisTermData")
      .mockResolvedValue({
        success: true,
        message: "已重新同步學籍學期資料",
        data: { id: 182, app_id: "APP-115-0-00182", previous_status: "error", new_status: "success", updated: true },
      } as any);
    const onResynced = jest.fn();

    render(
      <SisTermResyncCard
        applicationId={182}
        studentData={{ _term_data_status: "error" }}
        locale="zh"
        onResynced={onResynced}
      />
    );
    expect(screen.getByText("取得失敗")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /重新同步/ }));

    await waitFor(() => expect(onResynced).toHaveBeenCalledTimes(1));
    expect(resync).toHaveBeenCalledWith(182);
  });

  it("does not reload when SIS still has no term data", async () => {
    const resync = jest
      .spyOn(apiClient.admin, "resyncSisTermData")
      .mockResolvedValue({
        success: true,
        message: "學籍系統仍查無此申請學年度的學期資料，未變更",
        data: { id: 182, app_id: "APP-115-0-00182", previous_status: "error", new_status: "error", updated: false },
      } as any);
    const onResynced = jest.fn();

    render(
      <SisTermResyncCard
        applicationId={182}
        studentData={{ _term_data_status: "partial" }}
        locale="zh"
        onResynced={onResynced}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /重新同步/ }));

    await waitFor(() => expect(resync).toHaveBeenCalledTimes(1));
    expect(onResynced).not.toHaveBeenCalled();
  });
});
