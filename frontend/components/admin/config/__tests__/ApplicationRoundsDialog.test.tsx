/**
 * Tests for `ApplicationRoundsDialog` — the admin 多梯次申請 editor.
 *
 * Spies on the REAL apiClient singleton (a factory jest.mock of "@/lib/api"
 * does not intercept the component's import under this repo's ESM jest setup).
 */
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApplicationRoundsDialog } from "../ApplicationRoundsDialog";
import { apiClient } from "@/lib/api";
import type { ScholarshipConfiguration } from "@/lib/api/types";

const CONFIG = { id: 7, config_name: "博士生獎學金 115" } as ScholarshipConfiguration;

const roundsPayload = (rounds: unknown[] = []) => ({
  success: true,
  message: "ok",
  data: {
    configuration_id: 7,
    first_round: {
      round_number: 1,
      application_start_date: "2026-09-01T00:00:00Z",
      application_end_date: "2026-09-30T15:59:00Z",
    },
    current_application_round: null,
    available_sub_types: ["nstc", "moe_1w"],
    rounds,
  },
});

beforeEach(() => {
  jest.spyOn(apiClient.admin, "getSubTypeTranslations").mockResolvedValue({
    success: true,
    message: "ok",
    data: { zh: { nstc: "國科會", moe_1w: "教育部(一萬)" }, en: {} },
  } as any);
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("ApplicationRoundsDialog", () => {
  it("adds a second round and saves only the ticked sub-types", async () => {
    jest.spyOn(apiClient.admin, "getApplicationRounds").mockResolvedValue(roundsPayload() as any);
    const update = jest
      .spyOn(apiClient.admin, "updateApplicationRounds")
      .mockResolvedValue(roundsPayload() as any);
    const onSaved = jest.fn();
    const onOpenChange = jest.fn();

    render(
      <ApplicationRoundsDialog open configuration={CONFIG} onOpenChange={onOpenChange} onSaved={onSaved} />
    );

    expect(await screen.findByText(/目前只有一個梯次/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /新增梯次/ }));

    expect(screen.getByText("第二梯次")).toBeInTheDocument();
    // Every sub-type starts ticked; untick 教育部
    fireEvent.click(screen.getByLabelText("教育部(一萬)"));
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    const [configId, rounds] = update.mock.calls[0];
    expect(configId).toBe(7);
    expect(rounds).toHaveLength(1);
    expect(rounds[0]).toMatchObject({ round_number: 2, open_sub_types: ["nstc"], college_review_start: null });
    expect(new Date(rounds[0].application_start_date).toISOString()).toBe("2026-09-30T15:59:00.000Z");
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("keeps the dialog open when the backend refuses", async () => {
    jest.spyOn(apiClient.admin, "getApplicationRounds").mockResolvedValue(
      roundsPayload([
        {
          id: 1,
          round_number: 2,
          application_start_date: "2026-10-05T00:00:00Z",
          application_end_date: "2026-10-20T00:00:00Z",
          open_sub_types: ["nstc"],
        },
      ]) as any
    );
    jest.spyOn(apiClient.admin, "updateApplicationRounds").mockResolvedValue({
      success: false,
      message: "以下梯次已有申請，無法刪除：第二梯次（3 件）",
      data: undefined,
    } as any);
    const onSaved = jest.fn();
    const onOpenChange = jest.fn();

    render(
      <ApplicationRoundsDialog open configuration={CONFIG} onOpenChange={onOpenChange} onSaved={onSaved} />
    );

    expect(await screen.findByText("第二梯次")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "刪除第二梯次" }));
    expect(screen.queryByText("第二梯次")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(apiClient.admin.updateApplicationRounds).toHaveBeenCalledWith(7, []));
    expect(onSaved).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
