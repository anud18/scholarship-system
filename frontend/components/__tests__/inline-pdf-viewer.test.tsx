import React, { useEffect } from "react";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { InlinePdfViewer } from "../inline-pdf-viewer";

// Mock react-pdf so we don't load real pdf.js in jsdom. The mock exposes
// `__setSuccess(numPages)` / `__setError(err)` / `__renderAllPages()` to
// drive the lifecycle from each test.
//
// Real react-pdf v9: <Document> calls onLoadSuccess synchronously-ish after
// parsing the PDF, but each <Page>'s `onRenderSuccess` fires later, after
// pdf.js paints the canvas. The mock mirrors that by NOT calling
// onRenderSuccess automatically — tests opt in to "all pages rendered" via
// `__renderAllPages()`.
jest.mock("react-pdf", () => {
  type LoadCb = (info: { numPages: number }) => void;
  type ErrCb = (err: Error) => void;
  const handlers: { load?: LoadCb; err?: ErrCb } = {};
  const pageRenderCallbacks: Array<() => void> = [];

  const Document = (props: {
    onLoadSuccess?: LoadCb;
    onLoadError?: ErrCb;
    children?: React.ReactNode;
  }) => {
    handlers.load = props.onLoadSuccess;
    handlers.err = props.onLoadError;
    // NOTE: don't reset pageRenderCallbacks here — Page's useEffect cleanup
    // manages add/remove. Resetting on every Document render would wipe
    // registrations that survived through re-renders.
    return <div data-testid="pdf-document">{props.children}</div>;
  };

  const Page = ({
    pageNumber,
    onRenderSuccess,
  }: {
    pageNumber: number;
    onRenderSuccess?: () => void;
  }) => {
    // Register the page's render callback so tests can fire them all at once.
    useEffect(() => {
      const cb = onRenderSuccess;
      if (!cb) return;
      pageRenderCallbacks.push(cb);
      return () => {
        const i = pageRenderCallbacks.indexOf(cb);
        if (i >= 0) pageRenderCallbacks.splice(i, 1);
      };
    }, [onRenderSuccess]);
    return (
      <div data-testid={`pdf-page-${pageNumber}`} style={{ height: 800 }}>
        page {pageNumber}
      </div>
    );
  };

  return {
    Document,
    Page,
    pdfjs: { GlobalWorkerOptions: { workerSrc: "" }, version: "x" },
    __setSuccess: (n: number) => handlers.load?.({ numPages: n }),
    __setError: (e: Error) => handlers.err?.(e),
    __renderAllPages: () => {
      // Copy to avoid mutation while iterating (callbacks unregister via effect cleanup).
      const cbs = [...pageRenderCallbacks];
      cbs.forEach((cb) => cb());
    },
    __renderedPageCount: () => pageRenderCallbacks.length,
  };
});

// Mock the worker side-effect import so it doesn't blow up jsdom.
jest.mock("@/lib/pdf-worker", () => ({}));

// Spy on the download helper so tests can assert without real anchor clicks.
jest.mock("@/lib/utils/download", () => ({
  ...jest.requireActual("@/lib/utils/download"),
  triggerFileDownload: jest.fn(),
}));

// react-pdf bundles CSS we don't need under jsdom.
jest.mock("react-pdf/dist/Page/AnnotationLayer.css", () => ({}), { virtual: true });
jest.mock("react-pdf/dist/Page/TextLayer.css", () => ({}), { virtual: true });

const reactPdf = jest.requireMock("react-pdf") as {
  __setSuccess: (n: number) => void;
  __setError: (e: Error) => void;
  __renderAllPages: () => void;
};

/**
 * Define scroll metrics with a browser-like scrollTop: writes are clamped to
 * [0, scrollHeight - clientHeight] and any change dispatches a real scroll
 * event. This mirrors the mechanism behind the zoom-clamp gate-bypass this
 * suite regression-tests: in a browser, a programmatic scrollTop write (or a
 * content resize) that lands past the max is clamped to the bottom and fires
 * a scroll event.
 */
function setScrollMetrics(
  el: HTMLElement,
  {
    scrollHeight,
    clientHeight,
    scrollTop,
  }: { scrollHeight: number; clientHeight: number; scrollTop: number },
) {
  Object.defineProperty(el, "scrollHeight", {
    configurable: true,
    writable: true,
    value: scrollHeight,
  });
  Object.defineProperty(el, "clientHeight", {
    configurable: true,
    writable: true,
    value: clientHeight,
  });
  let current = scrollTop;
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    get: () => current,
    set: (v: number) => {
      const max = Math.max(0, (el.scrollHeight as number) - (el.clientHeight as number));
      const next = Math.max(0, Math.min(v, max));
      if (next !== current) {
        current = next;
        el.dispatchEvent(new Event("scroll"));
      }
    },
  });
}

function flushRaf() {
  return new Promise<void>((resolve) =>
    requestAnimationFrame(() => resolve()),
  );
}

function getScroller(container: HTMLElement): HTMLElement {
  const scroller = container.querySelector(
    "[data-testid='pdf-scroll-container']",
  ) as HTMLElement;
  expect(scroller).not.toBeNull();
  return scroller;
}

describe("InlinePdfViewer", () => {
  it("renders one <Page> per numPages after onLoadSuccess", () => {
    render(<InlinePdfViewer url="/fake.pdf" />);
    act(() => reactPdf.__setSuccess(3));
    expect(screen.getByTestId("pdf-page-1")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-page-2")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-page-3")).toBeInTheDocument();
  });

  it("fires onReachedBottom exactly once when the user scrolls to the bottom", () => {
    const onReached = jest.fn();
    const { container } = render(
      <InlinePdfViewer url="/fake.pdf" onReachedBottom={onReached} />,
    );
    act(() => reactPdf.__setSuccess(2));
    const scroller = getScroller(container);

    // Initial scroll, not yet at bottom.
    setScrollMetrics(scroller, { scrollHeight: 2000, clientHeight: 500, scrollTop: 100 });
    fireEvent.scroll(scroller);
    expect(onReached).not.toHaveBeenCalled();

    // Scroll to the bottom (within the 8px slack).
    setScrollMetrics(scroller, { scrollHeight: 2000, clientHeight: 500, scrollTop: 1495 });
    fireEvent.scroll(scroller);
    expect(onReached).toHaveBeenCalledTimes(1);

    // Bouncing back should NOT re-fire.
    setScrollMetrics(scroller, { scrollHeight: 2000, clientHeight: 500, scrollTop: 200 });
    fireEvent.scroll(scroller);
    expect(onReached).toHaveBeenCalledTimes(1);
  });

  it("fires onReachedBottom on mount-after-load when the document fits the container — but only AFTER all pages report onRenderSuccess", async () => {
    const onReached = jest.fn();
    const { container } = render(
      <InlinePdfViewer url="/fake.pdf" onReachedBottom={onReached} />,
    );
    const scroller = getScroller(container);
    setScrollMetrics(scroller, { scrollHeight: 400, clientHeight: 500, scrollTop: 0 });

    // onLoadSuccess alone (without page render) must NOT auto-latch. This is
    // the race that would otherwise let users skip the gate.
    await act(async () => {
      reactPdf.__setSuccess(1);
      await flushRaf();
    });
    expect(onReached).not.toHaveBeenCalled();

    const reactPdfFull = jest.requireMock("react-pdf") as {
      __renderedPageCount: () => number;
    };
    expect(reactPdfFull.__renderedPageCount()).toBe(1);

    // After every page reports render success, the fits-without-overflow
    // check runs and latches.
    await act(async () => {
      reactPdf.__renderAllPages();
    });
    // The effect schedules an rAF inside; flush it.
    await act(async () => {
      await flushRaf();
    });
    expect(onReached).toHaveBeenCalledTimes(1);
  });

  it("does NOT auto-latch on mount when the rendered document overflows the container", async () => {
    const onReached = jest.fn();
    const { container } = render(
      <InlinePdfViewer url="/fake.pdf" onReachedBottom={onReached} />,
    );
    const scroller = getScroller(container);
    // After all pages render, scrollHeight (1600) >> clientHeight (500)
    setScrollMetrics(scroller, { scrollHeight: 1600, clientHeight: 500, scrollTop: 0 });

    await act(async () => {
      reactPdf.__setSuccess(2);
      await flushRaf();
    });
    await act(async () => {
      reactPdf.__renderAllPages();
    });
    await act(async () => {
      await flushRaf();
    });

    expect(onReached).not.toHaveBeenCalled();
  });

  it("zoom controls change the zoom level within [50%, 300%] and reset restores 100%", () => {
    render(<InlinePdfViewer url="/fake.pdf" />);

    // Disabled until the document loads.
    expect(screen.getByTestId("pdf-zoom-in")).toBeDisabled();
    expect(screen.getByTestId("pdf-zoom-out")).toBeDisabled();

    act(() => reactPdf.__setSuccess(1));
    expect(screen.getByTestId("pdf-zoom-level")).toHaveTextContent("100%");

    fireEvent.click(screen.getByTestId("pdf-zoom-in"));
    expect(screen.getByTestId("pdf-zoom-level")).toHaveTextContent("125%");

    // Clamp at MIN_SCALE (50%): 125 → 100 → 75 → 50, then the button disables.
    const zoomOut = screen.getByTestId("pdf-zoom-out");
    fireEvent.click(zoomOut);
    fireEvent.click(zoomOut);
    fireEvent.click(zoomOut);
    expect(screen.getByTestId("pdf-zoom-level")).toHaveTextContent("50%");
    expect(zoomOut).toBeDisabled();

    fireEvent.click(screen.getByTestId("pdf-zoom-reset"));
    expect(screen.getByTestId("pdf-zoom-level")).toHaveTextContent("100%");
    expect(screen.getByTestId("pdf-zoom-reset")).toBeDisabled();
  });

  it("regression: the scroll-restore clamp during a zoom transition must NOT latch the reading gate", async () => {
    const onReached = jest.fn();
    const { container } = render(
      <InlinePdfViewer url="/fake.pdf" onReachedBottom={onReached} />,
    );
    const scroller = getScroller(container);
    setScrollMetrics(scroller, { scrollHeight: 1600, clientHeight: 500, scrollTop: 0 });

    await act(async () => {
      reactPdf.__setSuccess(2);
      await flushRaf();
    });
    await act(async () => {
      reactPdf.__renderAllPages();
    });
    await act(async () => {
      await flushRaf();
    });
    expect(onReached).not.toHaveBeenCalled();

    // User scrolls partway down (not latched).
    act(() => {
      scroller.scrollTop = 1000;
    });
    expect(onReached).not.toHaveBeenCalled();

    // Zoom out to 75%. The component's restore writes scrollTop = 750; in the
    // browser the later canvas shrink clamps scrollTop to the new bottom and
    // fires a scroll event — the settling window must swallow all of it.
    fireEvent.click(screen.getByTestId("pdf-zoom-out"));
    // Simulate the passive canvas resize: content shrinks, browser clamps the
    // 750 restore to the new max (1200 - 500 = 700 = bottom) and fires scroll.
    setScrollMetrics(scroller, { scrollHeight: 1200, clientHeight: 500, scrollTop: 750 });
    act(() => {
      scroller.scrollTop = 9999; // clamped to 700 → dispatches scroll at bottom
    });
    expect(onReached).not.toHaveBeenCalled();

    // Pages finish rendering at 75%; the settle window closes.
    await act(async () => {
      reactPdf.__renderAllPages();
    });
    await act(async () => {
      await flushRaf();
    });
    expect(onReached).not.toHaveBeenCalled();

    // Even a genuine scroll to the bottom at 75% must not latch (content
    // below 100% is not legible reading), and the hint says so.
    fireEvent.scroll(scroller);
    expect(onReached).not.toHaveBeenCalled();
    expect(screen.getByTestId("pdf-zoom-hint")).toBeInTheDocument();

    // Back at 100%: restore targets 700 / 0.75 ≈ 933 in the regrown layout.
    fireEvent.click(screen.getByTestId("pdf-zoom-reset"));
    setScrollMetrics(scroller, { scrollHeight: 1600, clientHeight: 500, scrollTop: 700 });
    await act(async () => {
      reactPdf.__renderAllPages();
    });
    await act(async () => {
      await flushRaf();
    });
    // Not at the bottom (1600 - 933 - 500 = 167 > 8) → still not latched.
    expect(onReached).not.toHaveBeenCalled();
    expect(screen.queryByTestId("pdf-zoom-hint")).not.toBeInTheDocument();

    // Now genuinely reach the bottom at 100% → latches exactly once.
    act(() => {
      scroller.scrollTop = 1600 - 500;
    });
    expect(onReached).toHaveBeenCalledTimes(1);
  });

  it("re-applies the zoom scroll restore after the new-scale layout settles (position kept)", async () => {
    const { container } = render(<InlinePdfViewer url="/fake.pdf" />);
    const scroller = getScroller(container);
    setScrollMetrics(scroller, { scrollHeight: 1600, clientHeight: 500, scrollTop: 0 });

    await act(async () => {
      reactPdf.__setSuccess(2);
      await flushRaf();
    });
    await act(async () => {
      reactPdf.__renderAllPages();
    });
    await act(async () => {
      await flushRaf();
    });

    act(() => {
      scroller.scrollTop = 900;
    });

    // Zoom in to 125%: the immediate restore targets 1125, but the old layout
    // caps scrollTop at 1100 — the browser clamps. Once the canvases grow
    // (scrollHeight 2000), the settle pass must re-apply the true target.
    fireEvent.click(screen.getByTestId("pdf-zoom-in"));
    setScrollMetrics(scroller, { scrollHeight: 2000, clientHeight: 500, scrollTop: scroller.scrollTop });
    await act(async () => {
      reactPdf.__renderAllPages();
    });
    await act(async () => {
      await flushRaf();
    });
    expect(scroller.scrollTop).toBe(1125);
  });

  it("download button delegates to triggerFileDownload with the proxy URL and filename", () => {
    const { triggerFileDownload } = jest.requireMock("@/lib/utils/download") as {
      triggerFileDownload: jest.Mock;
    };
    triggerFileDownload.mockClear();

    render(
      <InlinePdfViewer url="/api/v1/preview/system-docs?key=regulations_url" downloadFilename="要點.pdf" />,
    );
    act(() => reactPdf.__setSuccess(1));

    fireEvent.click(screen.getByTestId("pdf-download"));
    expect(triggerFileDownload).toHaveBeenCalledWith(
      "/api/v1/preview/system-docs?key=regulations_url",
      "要點.pdf",
    );
  });

  it("fires onLoadError and never fires onReachedBottom when load fails — and keeps download/open-in-new-tab available", () => {
    const onReached = jest.fn();
    const onErr = jest.fn();
    render(
      <InlinePdfViewer
        url="/broken.pdf"
        onReachedBottom={onReached}
        onLoadError={onErr}
      />,
    );

    const err = new Error("boom");
    act(() => reactPdf.__setError(err));

    expect(onErr).toHaveBeenCalledWith(err);
    expect(onReached).not.toHaveBeenCalled();
    expect(screen.getByText(/重新載入|Reload/)).toBeInTheDocument();
    // The file may still be downloadable even when pdf.js can't render it, so
    // the toolbar's escape hatches must survive the error state.
    expect(screen.getByTestId("pdf-download")).toBeEnabled();
    expect(screen.getByTestId("pdf-open-new-tab")).toBeEnabled();
    expect(screen.getByTestId("pdf-zoom-in")).toBeDisabled();
  });
});
