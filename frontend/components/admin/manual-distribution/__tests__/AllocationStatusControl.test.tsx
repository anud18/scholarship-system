import { render, screen, fireEvent } from "@testing-library/react";
import { AllocationStatusControl } from "../AllocationStatusControl";

describe("AllocationStatusControl", () => {
  it("normal: 正常 active, 撤銷/停發 actionable and call handlers", () => {
    const onRevoke = jest.fn();
    const onSuspend = jest.fn();
    render(
      <AllocationStatusControl status="normal" onRevoke={onRevoke} onSuspend={onSuspend} />
    );

    expect(screen.getByRole("button", { name: "正常" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );

    const revoke = screen.getByRole("button", { name: "撤銷" });
    const suspend = screen.getByRole("button", { name: "停發" });
    expect(revoke).toBeEnabled();
    expect(suspend).toBeEnabled();

    fireEvent.click(revoke);
    expect(onRevoke).toHaveBeenCalledTimes(1);
    fireEvent.click(suspend);
    expect(onSuspend).toHaveBeenCalledTimes(1);
  });

  it("revoked: 撤銷 active, control read-only (no handler fires), reason in tooltip", () => {
    const onRevoke = jest.fn();
    const onSuspend = jest.fn();
    render(
      <AllocationStatusControl
        status="revoked"
        reason="違反第三條"
        onRevoke={onRevoke}
        onSuspend={onSuspend}
      />
    );

    expect(screen.getByRole("button", { name: "撤銷" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    // Terminal → every segment is disabled; clicks are inert.
    fireEvent.click(screen.getByRole("button", { name: "停發" }));
    fireEvent.click(screen.getByRole("button", { name: "撤銷" }));
    expect(onRevoke).not.toHaveBeenCalled();
    expect(onSuspend).not.toHaveBeenCalled();

    expect(screen.getByRole("group", { name: "分發狀態" })).toHaveAttribute(
      "title",
      "原因：違反第三條"
    );
  });

  it("suspended: 停發 active", () => {
    render(
      <AllocationStatusControl status="suspended" onRevoke={jest.fn()} onSuspend={jest.fn()} />
    );
    expect(screen.getByRole("button", { name: "停發" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  });
});
