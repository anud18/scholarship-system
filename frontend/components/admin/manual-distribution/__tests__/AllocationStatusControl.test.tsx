import { render, screen, fireEvent } from "@testing-library/react";
import { AllocationStatusControl } from "../AllocationStatusControl";

const handlers = () => ({
  onRevoke: jest.fn(),
  onSuspend: jest.fn(),
  onRestore: jest.fn(),
});

describe("AllocationStatusControl", () => {
  it("normal: 正常 active, 撤銷/停發 actionable; 正常 inert", () => {
    const h = handlers();
    render(<AllocationStatusControl status="normal" {...h} />);

    expect(screen.getByRole("button", { name: "正常" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    const revoke = screen.getByRole("button", { name: "撤銷" });
    const suspend = screen.getByRole("button", { name: "停發" });
    expect(revoke).toBeEnabled();
    expect(suspend).toBeEnabled();
    expect(screen.getByRole("button", { name: "正常" })).toBeDisabled();

    fireEvent.click(revoke);
    expect(h.onRevoke).toHaveBeenCalledTimes(1);
    fireEvent.click(suspend);
    expect(h.onSuspend).toHaveBeenCalledTimes(1);
    expect(h.onRestore).not.toHaveBeenCalled();
  });

  it("revoked: 撤銷 active; 正常 restores; 停發 inert; reason in tooltip", () => {
    const h = handlers();
    render(
      <AllocationStatusControl status="revoked" reason="違反第三條" {...h} />
    );

    expect(screen.getByRole("button", { name: "撤銷" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );

    // 正常 is the live restore action.
    const normal = screen.getByRole("button", { name: "正常" });
    expect(normal).toBeEnabled();
    fireEvent.click(normal);
    expect(h.onRestore).toHaveBeenCalledTimes(1);

    // The other action segment is inert while terminal.
    const suspend = screen.getByRole("button", { name: "停發" });
    expect(suspend).toBeDisabled();
    fireEvent.click(suspend);
    expect(h.onSuspend).not.toHaveBeenCalled();
    expect(h.onRevoke).not.toHaveBeenCalled();

    expect(screen.getByRole("group", { name: "分發狀態" })).toHaveAttribute(
      "title",
      "原因：違反第三條"
    );
  });

  it("suspended: 停發 active; 正常 restores", () => {
    const h = handlers();
    render(<AllocationStatusControl status="suspended" {...h} />);
    expect(screen.getByRole("button", { name: "停發" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    fireEvent.click(screen.getByRole("button", { name: "正常" }));
    expect(h.onRestore).toHaveBeenCalledTimes(1);
  });

  // A student with no allocation yet (pre-確認分發) is just as actionable —
  // that is the whole point of showing the control on every row.
  it("hasAllocation=false: 撤銷/停發 still fire; copy says 本次分發將略過", () => {
    const h = handlers();
    render(
      <AllocationStatusControl status="normal" hasAllocation={false} {...h} />
    );

    const revoke = screen.getByRole("button", { name: "撤銷" });
    const suspend = screen.getByRole("button", { name: "停發" });
    expect(revoke).toBeEnabled();
    expect(suspend).toBeEnabled();
    expect(revoke).toHaveAttribute(
      "title",
      expect.stringContaining("本次分發將略過")
    );
    expect(suspend).toHaveAttribute(
      "title",
      expect.stringContaining("本次分發將略過")
    );
    expect(screen.getByRole("group", { name: "分發狀態" })).toHaveAttribute(
      "title",
      "尚未核配獎學金，仍可預先撤銷／停發以排除於本次分發"
    );

    fireEvent.click(revoke);
    expect(h.onRevoke).toHaveBeenCalledTimes(1);
    fireEvent.click(suspend);
    expect(h.onSuspend).toHaveBeenCalledTimes(1);
  });

  it("hasAllocation defaults to true: allocated-row tooltips are unchanged", () => {
    const h = handlers();
    render(<AllocationStatusControl status="normal" {...h} />);
    expect(screen.getByRole("button", { name: "撤銷" })).toHaveAttribute(
      "title",
      "撤銷此學生獎學金（違反獎學金要點）"
    );
    expect(screen.getByRole("button", { name: "停發" })).toHaveAttribute(
      "title",
      "停發此學生獎學金（休學/退學/畢業）"
    );
    expect(screen.getByRole("group", { name: "分發狀態" })).not.toHaveAttribute(
      "title"
    );
  });
});
