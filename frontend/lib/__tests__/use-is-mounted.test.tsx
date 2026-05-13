/**
 * Tests for `lib/use-is-mounted.ts:useIsMounted`.
 *
 * This hook returns `false` on the initial render and `true` after
 * mount. Used everywhere we need to avoid SSR/CSR hydration mismatches
 * (e.g., reading `window`, `localStorage`, or rendering charts).
 *
 * Regression risk:
 * - Returns `true` on initial render → SSR HTML differs from client
 *   HTML → React hydration warning + visible flicker.
 * - Returns `false` after mount → conditional renders never show,
 *   client features silently broken.
 *
 * 3 cases pinning the SSR-safe contract.
 */
import React from "react";
import { render, screen, act } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import { useIsMounted } from "../use-is-mounted";

describe("useIsMounted", () => {
  it("returns true after mount (synchronous re-render via useEffect)", () => {
    /** React Testing Library runs useEffect synchronously after the
     * initial render, so the returned value after `renderHook` is
     * already the post-mount value. */
    const { result } = renderHook(() => useIsMounted());
    expect(result.current).toBe(true);
  });

  it("returns false during the initial synchronous render path", () => {
    /** To capture the pre-mount state, render a component that captures
     * the value on its first render. We use a ref to record the value
     * before useEffect runs. */
    const captured: boolean[] = [];

    function Probe() {
      const isMounted = useIsMounted();
      captured.push(isMounted);
      return <div data-testid="probe">{String(isMounted)}</div>;
    }

    render(<Probe />);

    // The first captured value should be `false` (pre-mount).
    expect(captured[0]).toBe(false);
    // After useEffect runs, a re-render happens and captures `true`.
    expect(captured[captured.length - 1]).toBe(true);
  });

  it("renders the post-mount string in the DOM", () => {
    /** End-to-end: the DOM should show 'true' after mount. This is the
     * shape consumers actually depend on. */
    function Probe() {
      const isMounted = useIsMounted();
      return <span data-testid="probe">{String(isMounted)}</span>;
    }

    render(<Probe />);
    expect(screen.getByTestId("probe").textContent).toBe("true");
  });
});
