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
});
