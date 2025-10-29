import React from "react";
import { renderHook } from "@testing-library/react";
import { useIsMobile } from "../use-mobile";

// Mock window.matchMedia
const mockMatchMedia = jest.fn();

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: mockMatchMedia,
});

// Mock window.innerWidth
Object.defineProperty(window, "innerWidth", {
  writable: true,
  value: 1024,
});

describe("useIsMobile Hook", () => {
  let mockMediaQueryList: {
    matches: boolean;
    addEventListener: jest.Mock;
    removeEventListener: jest.Mock;
  };

  beforeEach(() => {
    mockMediaQueryList = {
      matches: false,
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    };
    mockMatchMedia.mockReturnValue(mockMediaQueryList);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("should initialize as undefined and then set correct mobile state", () => {
    // Set desktop width
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: 1024,
    });

    const { result } = renderHook(() => useIsMobile());

    // Initial state should be false (since we're on desktop width)
    expect(result.current).toBe(false);
  });

  it("should return true for mobile width", () => {
    // Set mobile width
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: 500,
    });

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(true);
  });

  it("should return false for desktop width", () => {
    // Set desktop width
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: 1024,
    });

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(false);
  });

  it("should return true for width at mobile breakpoint boundary", () => {
    // Set width exactly at mobile breakpoint (767px)
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: 767,
    });

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(true);
  });

  it("should return false for width at desktop breakpoint boundary", () => {
    // Set width exactly at desktop breakpoint (768px)
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: 768,
    });

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(false);
  });

  it("should set up media query listener correctly", () => {
    renderHook(() => useIsMobile());

    expect(mockMatchMedia).toHaveBeenCalledWith("(max-width: 767px)");
    expect(mockMediaQueryList.addEventListener).toHaveBeenCalledWith(
      "change",
      expect.any(Function)
    );
  });

  it("should clean up event listener on unmount", () => {
    const { unmount } = renderHook(() => useIsMobile());

    unmount();

    expect(mockMediaQueryList.removeEventListener).toHaveBeenCalledWith(
      "change",
      expect.any(Function)
    );
  });

  it("should respond to media query changes", () => {
    let changeHandler: () => void;

    mockMediaQueryList.addEventListener.mockImplementation((event, handler) => {
      if (event === "change") {
        changeHandler = handler;
      }
    });

    // Start with desktop width
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: 1024,
    });

    const { result, rerender } = renderHook(() => useIsMobile());

    expect(result.current).toBe(false);

    // Simulate window resize to mobile
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: 500,
    });

    // Trigger the change handler
    if (changeHandler!) {
      changeHandler();
    }

    rerender();

    expect(result.current).toBe(true);
  });

  it("should handle undefined window.innerWidth gracefully", () => {
    // Mock innerWidth as undefined
    Object.defineProperty(window, "innerWidth", {
      writable: true,
      value: undefined,
    });

    const { result } = renderHook(() => useIsMobile());

    // Should still return a boolean value (false for undefined)
    expect(typeof result.current).toBe("boolean");
  });

  it("should always return boolean value", () => {
    const { result } = renderHook(() => useIsMobile());

    expect(typeof result.current).toBe("boolean");
  });

  describe("breakpoint calculations", () => {
    const MOBILE_BREAKPOINT = 768;

    it("should use correct breakpoint constant", () => {
      renderHook(() => useIsMobile());

      expect(mockMatchMedia).toHaveBeenCalledWith(
        `(max-width: ${MOBILE_BREAKPOINT - 1}px)`
      );
    });

    it("should classify widths correctly around breakpoint", () => {
      // Test various widths around the breakpoint
      const testCases = [
        { width: 767, expectedMobile: true },
        { width: 768, expectedMobile: false },
        { width: 320, expectedMobile: true },
        { width: 1920, expectedMobile: false },
      ];

      testCases.forEach(({ width, expectedMobile }) => {
        Object.defineProperty(window, "innerWidth", {
          writable: true,
          value: width,
        });

        const { result } = renderHook(() => useIsMobile());
        expect(result.current).toBe(expectedMobile);
      });
    });
  });
});
