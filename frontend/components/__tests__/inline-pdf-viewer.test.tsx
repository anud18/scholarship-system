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

// react-pdf bundles CSS we don't need under jsdom.
jest.mock("react-pdf/dist/Page/AnnotationLayer.css", () => ({}), { virtual: true });
jest.mock("react-pdf/dist/Page/TextLayer.css", () => ({}), { virtual: true });

const reactPdf = jest.requireMock("react-pdf") as {
  __setSuccess: (n: number) => void;
  __setError: (e: Error) => void;
  __renderAllPages: () => void;
};

function setScrollMetrics(
  el: HTMLElement,
  {
    scrollHeight,
    clientHeight,
    scrollTop,
  }: { scrollHeight: number; clientHeight: number; scrollTop: number },
) {
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: clientHeight });
  Object.defineProperty(el, "scrollTop", { configurable: true, value: scrollTop });
}

function flushRaf() {
  return new Promise<void>((resolve) =>
    requestAnimationFrame(() => resolve()),
  );
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

    const scroller = container.querySelector(
      "[data-testid='pdf-scroll-container']",
    ) as HTMLElement;
    expect(scroller).not.toBeNull();

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

    const scroller = container.querySelector(
      "[data-testid='pdf-scroll-container']",
    ) as HTMLElement;
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

    const scroller = container.querySelector(
      "[data-testid='pdf-scroll-container']",
    ) as HTMLElement;
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

  it("fires onLoadError and never fires onReachedBottom when load fails", () => {
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
  });
});
