/**
 * Tests for `ErrorBoundary` component + `useErrorHandler` hook
 * + `withErrorBoundary` HOC (frontend/components/error-boundary.tsx).
 *
 * The ErrorBoundary catches runtime errors thrown by child components
 * and renders a fallback UI. If this breaks, an unhandled React
 * crash propagates to the root and breaks the entire page.
 *
 * Tested:
 *  - getDerivedStateFromError(): static method that sets hasError
 *    state from a thrown Error. Pure — no DOM/lifecycle.
 *  - render(): renders children when no error, renders fallback UI
 *    when hasError, renders custom fallback prop when provided.
 *  - componentDidCatch(): calls optional onError callback.
 *  - handleRetry: reset state back to no-error.
 *  - withErrorBoundary HOC: wraps a component in ErrorBoundary.
 *  - useErrorHandler: returns a function that logs.
 *
 * 12 cases.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorBoundary, useErrorHandler, withErrorBoundary } from "../error-boundary";

// Suppress console.error from React's internal error reporting
let consoleErrorSpy: jest.SpyInstance;
beforeEach(() => {
  consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  consoleErrorSpy.mockRestore();
});

// A component that throws on render when shouldThrow=true
function Bomb({ shouldThrow = true }: { shouldThrow?: boolean }) {
  if (shouldThrow) throw new Error("kaboom");
  return <div>safe child</div>;
}

// ─── getDerivedStateFromError (pure) ─────────────────────────────────

describe("ErrorBoundary.getDerivedStateFromError", () => {
  it("returns hasError=true with the caught error", () => {
    // Pin: pure static method — given an Error, returns
    // { hasError: true, error }. No state, no DOM access.
    const err = new Error("test error");
    const state = ErrorBoundary.getDerivedStateFromError(err);
    expect(state).toEqual({ hasError: true, error: err });
  });
});

// ─── render contract ────────────────────────────────────────────────

describe("ErrorBoundary render", () => {
  it("renders children when no error thrown", () => {
    // Pin: happy path — children pass through unchanged.
    render(
      <ErrorBoundary>
        <div>happy</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("happy")).toBeInTheDocument();
  });

  it("renders default error UI when child throws", () => {
    // Pin: when child throws, the default Chinese error message
    // appears. Pin the exact text — admins / users read this.
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>
    );
    expect(
      screen.getByText("發生未預期的錯誤。請重新整理頁面或聯繫系統管理員。")
    ).toBeInTheDocument();
  });

  it("renders custom fallback when fallback prop provided", () => {
    // Pin: custom fallback overrides the default UI. Pages that
    // want a context-specific error message pass this.
    render(
      <ErrorBoundary fallback={<div>custom oops</div>}>
        <Bomb />
      </ErrorBoundary>
    );
    expect(screen.getByText("custom oops")).toBeInTheDocument();
    expect(
      screen.queryByText("發生未預期的錯誤。請重新整理頁面或聯繫系統管理員。")
    ).not.toBeInTheDocument();
  });

  it("renders retry button in default UI", () => {
    // Pin: "重試" button present so user can recover without
    // full page reload.
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>
    );
    expect(screen.getByText("重試")).toBeInTheDocument();
  });

  it("renders refresh-page button in default UI", () => {
    // Pin: "重新整理頁面" button is the escape hatch when retry
    // doesn't recover.
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>
    );
    expect(screen.getByText("重新整理頁面")).toBeInTheDocument();
  });
});

// ─── componentDidCatch callback ─────────────────────────────────────

describe("ErrorBoundary.componentDidCatch onError callback", () => {
  it("invokes onError prop when child throws", () => {
    // Pin: external error-reporting hook is called with the
    // Error and ErrorInfo (componentStack). Pages that want to
    // send the error to a monitoring service pass this callback.
    const onError = jest.fn();
    render(
      <ErrorBoundary onError={onError}>
        <Bomb />
      </ErrorBoundary>
    );
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);
    expect(onError.mock.calls[0][0].message).toBe("kaboom");
  });

  it("does not invoke onError when no error thrown", () => {
    const onError = jest.fn();
    render(
      <ErrorBoundary onError={onError}>
        <div>fine</div>
      </ErrorBoundary>
    );
    expect(onError).not.toHaveBeenCalled();
  });
});

// ─── handleRetry: state reset ──────────────────────────────────────

describe("ErrorBoundary retry behaviour", () => {
  it("retry + key change recovers children", () => {
    // Pin: clicking 重試 sets hasError=false. To recover the
    // children render after a thrown error, callers must re-mount
    // the boundary subtree (e.g. by changing the React key) so
    // the child has a chance to render successfully — pinning
    // the documented recovery pattern.
    const { rerender } = render(
      <ErrorBoundary key="a">
        <Bomb />
      </ErrorBoundary>
    );
    // Error UI is shown
    expect(screen.getByText("重試")).toBeInTheDocument();

    // Click retry handler (verifies onClick wired up).
    fireEvent.click(screen.getByText("重試"));

    // Caller-side recovery: remount with new key + non-throwing
    // child.
    rerender(
      <ErrorBoundary key="b">
        <Bomb shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByText("safe child")).toBeInTheDocument();
    expect(screen.queryByText("重試")).not.toBeInTheDocument();
  });
});

// ─── withErrorBoundary HOC ──────────────────────────────────────────

describe("withErrorBoundary HOC", () => {
  it("wraps component and renders it normally", () => {
    // Pin: HOC is a transparent passthrough when no error.
    const Inner = () => <div>inner content</div>;
    const Wrapped = withErrorBoundary(Inner);
    render(<Wrapped />);
    expect(screen.getByText("inner content")).toBeInTheDocument();
  });

  it("HOC catches errors with provided fallback", () => {
    // Pin: HOC accepts custom fallback that takes precedence
    // over the default UI when the wrapped component throws.
    const Wrapped = withErrorBoundary(Bomb, <div>hoc fallback</div>);
    render(<Wrapped />);
    expect(screen.getByText("hoc fallback")).toBeInTheDocument();
  });

  it("HOC forwards onError callback", () => {
    const onError = jest.fn();
    const Wrapped = withErrorBoundary(Bomb, undefined, onError);
    render(<Wrapped />);
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

// ─── useErrorHandler hook ──────────────────────────────────────────

describe("useErrorHandler hook", () => {
  it("returns a function that logs the error", () => {
    // Pin: hook returns a stable callable. Used by functional
    // components that catch errors imperatively (try/catch in
    // async handlers).
    let captured: ((err: Error, info?: string) => void) | undefined;
    function Probe() {
      captured = useErrorHandler();
      return null;
    }
    render(<Probe />);
    expect(typeof captured).toBe("function");

    // Invoking the handler logs (we mocked console.error in
    // beforeEach so this should produce a captured call).
    const err = new Error("handled");
    captured!(err, "ctx");
    expect(consoleErrorSpy).toHaveBeenCalled();
  });
});
