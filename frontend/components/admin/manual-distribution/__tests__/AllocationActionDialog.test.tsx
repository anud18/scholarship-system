import React, { act } from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AllocationActionDialog } from "../AllocationActionDialog";
import { apiClient } from "@/lib/api";

jest.mock("@/lib/utils/logger", () => ({
  logger: { error: jest.fn(), debug: jest.fn(), info: jest.fn(), warn: jest.fn() },
}));

const mockRevokeAllocation = jest.fn().mockResolvedValue({ success: true });
const mockSuspendAllocation = jest.fn().mockResolvedValue({ success: true });

// Mock Radix Dialog to render inline (no portal / focus-trap issues in jsdom)
jest.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="dialog-content">{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <h2>{children}</h2>
  ),
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
    <p>{children}</p>
  ),
  DialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

// Mock Radix Select to render as a plain <select> (no portal issues)
jest.mock("@/components/ui/select", () => ({
  Select: ({
    children,
    value,
    onValueChange,
    disabled,
  }: {
    children: React.ReactNode;
    value: string;
    onValueChange: (v: string) => void;
    disabled?: boolean;
  }) => (
    <select
      value={value}
      onChange={e => onValueChange(e.target.value)}
      disabled={disabled}
      data-testid="suspend-select"
    >
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
  SelectValue: () => null,
  SelectContent: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
  SelectItem: ({
    children,
    value,
  }: {
    children: React.ReactNode;
    value: string;
  }) => <option value={value}>{children}</option>,
}));

const target = { applicationId: 7, studentName: "王小明" };

describe("AllocationActionDialog", () => {
  beforeEach(() => {
    jest.spyOn(apiClient.manualDistribution, "revokeAllocation").mockImplementation(mockRevokeAllocation);
    jest.spyOn(apiClient.manualDistribution, "suspendAllocation").mockImplementation(mockSuspendAllocation);
    mockRevokeAllocation.mockClear();
    mockSuspendAllocation.mockClear();
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("revoke mode: free-text reason, placeholder 違反獎學金要點, confirm disabled when empty", () => {
    render(
      <AllocationActionDialog
        mode="revoke"
        target={target}
        onClose={() => {}}
        onConfirmed={() => {}}
      />
    );
    expect(screen.getByPlaceholderText("違反獎學金要點")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "確認撤銷" })).toBeDisabled();
  });

  it("revoke mode: enabling + confirm calls revokeAllocation with trimmed reason", async () => {
    const onConfirmed = jest.fn();
    render(
      <AllocationActionDialog
        mode="revoke"
        target={target}
        onClose={() => {}}
        onConfirmed={onConfirmed}
      />
    );
    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText("違反獎學金要點"), {
        target: { value: "  違反第三條  " },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "確認撤銷" }));
    });
    await waitFor(() =>
      expect(mockRevokeAllocation).toHaveBeenCalledWith(7, "違反第三條")
    );
    expect(onConfirmed).toHaveBeenCalledWith("王小明");
  });

  it("suspend mode: composes 「label：note」 and calls suspendAllocation", async () => {
    const onConfirmed = jest.fn();
    render(
      <AllocationActionDialog
        mode="suspend"
        target={target}
        onClose={() => {}}
        onConfirmed={onConfirmed}
      />
    );
    // default option is 休學; add a note
    await act(async () => {
      fireEvent.change(screen.getByPlaceholderText("選填"), {
        target: { value: "已辦理休學" },
      });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "確認停發" }));
    });
    await waitFor(() =>
      expect(mockSuspendAllocation).toHaveBeenCalledWith(7, "休學：已辦理休學")
    );
    expect(onConfirmed).toHaveBeenCalledWith("王小明");
  });

  it("suspend mode: 其他 selected + empty note → confirm button disabled; typing note enables it", async () => {
    render(
      <AllocationActionDialog
        mode="suspend"
        target={target}
        onClose={() => {}}
        onConfirmed={() => {}}
      />
    );
    // Switch to 其他 via the mocked <select data-testid="suspend-select">
    await act(async () => {
      fireEvent.change(screen.getByTestId("suspend-select"), {
        target: { value: "其他" },
      });
    });
    // Note is still empty → confirm must be disabled
    expect(screen.getByRole("button", { name: "確認停發" })).toBeDisabled();

    // Type a note → confirm becomes enabled
    await act(async () => {
      fireEvent.change(
        screen.getByPlaceholderText("選擇「其他」時必填，請說明原因"),
        { target: { value: "因故停發" } }
      );
    });
    expect(screen.getByRole("button", { name: "確認停發" })).not.toBeDisabled();
  });
});
