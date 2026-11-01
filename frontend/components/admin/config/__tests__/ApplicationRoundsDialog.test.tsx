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

const roundsPayload = (rounds: unknown[] = [], firstRoundOpenSubTypes: string[] | null = null) => ({
  success: true,
  message: "ok",
  data: {
    configuration_id: 7,
    first_round_open_sub_types: firstRoundOpenSubTypes,
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
    // Every sub-type starts ticked; untick 教育部 in the new round
    fireEvent.click(document.getElementById("round-2-sub-moe_1w") as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    const [configId, body] = update.mock.calls[0];
    expect(configId).toBe(7);
    expect(body.first_round_open_sub_types).toBeNull();
    const rounds = body.rounds ?? [];
    expect(rounds).toHaveLength(1);
    expect(rounds[0]).toMatchObject({ round_number: 2, open_sub_types: ["nstc"] });
    expect(new Date(rounds[0].application_start_date).toISOString()).toBe("2026-09-30T15:59:00.000Z");
    // Review windows are pre-filled from the round's own window
    expect(rounds[0].college_review_start).toBe(rounds[0].application_start_date);
    expect(rounds[0].college_review_end).not.toBeNull();
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("labels the general window 第一梯次 and points to 編輯配置 for its dates", async () => {
    jest.spyOn(apiClient.admin, "getApplicationRounds").mockResolvedValue(roundsPayload() as any);
    render(<ApplicationRoundsDialog open configuration={CONFIG} onOpenChange={jest.fn()} />);

    expect(await screen.findByText("第一梯次")).toBeInTheDocument();
    expect(screen.getByText(/請於「編輯配置」的一般申請開始／截止時間修改/)).toBeInTheDocument();
    expect(screen.getByLabelText("開放所有子類別")).toBeChecked();
  });

  it("restricts 第一梯次 to the ticked sub-types", async () => {
    jest.spyOn(apiClient.admin, "getApplicationRounds").mockResolvedValue(roundsPayload() as any);
    const update = jest
      .spyOn(apiClient.admin, "updateApplicationRounds")
      .mockResolvedValue(roundsPayload() as any);
    render(<ApplicationRoundsDialog open configuration={CONFIG} onOpenChange={jest.fn()} />);

    fireEvent.click(await screen.findByLabelText("開放所有子類別"));
    fireEvent.click(screen.getByLabelText("國科會"));
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(7, { first_round_open_sub_types: ["moe_1w"], rounds: [] })
    );
  });

  it("re-opens 第一梯次 to every sub-type via 開放所有子類別", async () => {
    jest.spyOn(apiClient.admin, "getApplicationRounds").mockResolvedValue(roundsPayload([], ["nstc"]) as any);
    const update = jest
      .spyOn(apiClient.admin, "updateApplicationRounds")
      .mockResolvedValue(roundsPayload() as any);
    render(<ApplicationRoundsDialog open configuration={CONFIG} onOpenChange={jest.fn()} />);

    const openAll = await screen.findByLabelText("開放所有子類別");
    expect(openAll).not.toBeChecked();
    expect(screen.getByLabelText("教育部(一萬)")).not.toBeChecked();
    fireEvent.click(openAll);
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(7, { first_round_open_sub_types: null, rounds: [] })
    );
  });

  it("refuses to save 第一梯次 with no sub-type", async () => {
    jest.spyOn(apiClient.admin, "getApplicationRounds").mockResolvedValue(roundsPayload([], ["nstc"]) as any);
    const update = jest.spyOn(apiClient.admin, "updateApplicationRounds");
    render(<ApplicationRoundsDialog open configuration={CONFIG} onOpenChange={jest.fn()} />);

    fireEvent.click(await screen.findByLabelText("國科會"));
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect(update).not.toHaveBeenCalled();
  });

  it("never saves another configuration's rounds after a failed load", async () => {
    const getRounds = jest
      .spyOn(apiClient.admin, "getApplicationRounds")
      .mockResolvedValueOnce(
        roundsPayload([
          {
            id: 1,
            round_number: 2,
            application_start_date: "2026-10-05T00:00:00Z",
            application_end_date: "2026-10-20T00:00:00Z",
            open_sub_types: ["nstc"],
          },
        ]) as any
      )
      .mockResolvedValueOnce({ success: false, message: "配置不存在或您沒有存取權限", data: undefined } as any);
    const update = jest.spyOn(apiClient.admin, "updateApplicationRounds");

    const { rerender } = render(
      <ApplicationRoundsDialog open configuration={CONFIG} onOpenChange={jest.fn()} />
    );
    expect(await screen.findByText("第二梯次")).toBeInTheDocument();

    rerender(
      <ApplicationRoundsDialog
        open
        configuration={{ ...CONFIG, id: 8 } as ScholarshipConfiguration}
        onOpenChange={jest.fn()}
      />
    );
    await waitFor(() => expect(getRounds).toHaveBeenCalledWith(8));
    await waitFor(() => expect(screen.queryByText("第二梯次")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "儲存" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));
    expect(update).not.toHaveBeenCalled();
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

    await waitFor(() =>
      expect(apiClient.admin.updateApplicationRounds).toHaveBeenCalledWith(7, {
        first_round_open_sub_types: null,
        rounds: [],
      })
    );
    expect(onSaved).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
