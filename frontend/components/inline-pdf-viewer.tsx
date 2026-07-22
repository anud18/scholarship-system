"use client";

import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Document, Page } from "react-pdf";
import {
  AlertCircle,
  Download,
  ExternalLink,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { triggerFileDownload } from "@/lib/utils/download";

// Side-effect import: configures pdfjs.GlobalWorkerOptions.workerSrc.
import "@/lib/pdf-worker";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

interface InlinePdfViewerProps {
  url: string;
  // Tailwind classes for sizing the scroll container, e.g.
  // `h-[min(700px,calc(90vh-200px))]`. Required in practice — the
  // container has no intrinsic height without one. The zoom/download
  // toolbar adds its own height on top of this.
  className?: string;
  onReachedBottom?: () => void;
  onLoadError?: (err: Error) => void;
  // Filename used by the toolbar's download button.
  downloadFilename?: string;
  locale?: "zh" | "en";
}

const SLACK_PX = 8;
const MIN_SCALE = 0.5;
const MAX_SCALE = 3;
const SCALE_STEP = 0.25;
const DEFAULT_SCALE = 1;

const LABELS = {
  zh: {
    loading: "載入中…",
    error: "無法載入文件",
    reload: "重新載入",
    zoomIn: "放大",
    zoomOut: "縮小",
    resetZoom: "重設縮放",
    download: "下載",
    openInNewTab: "另開新視窗",
  },
  en: {
    loading: "Loading…",
    error: "Failed to load document",
    reload: "Reload",
    zoomIn: "Zoom in",
    zoomOut: "Zoom out",
    resetZoom: "Reset zoom",
    download: "Download",
    openInNewTab: "Open in new tab",
  },
} as const;

export function InlinePdfViewer({
  url,
  className,
  onReachedBottom,
  onLoadError,
  downloadFilename,
  locale = "zh",
}: InlinePdfViewerProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [renderedCount, setRenderedCount] = useState(0);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [scale, setScale] = useState(DEFAULT_SCALE);

  const latched = useRef(false);
  useEffect(() => {
    latched.current = false;
  }, [url, reloadToken]);

  const fireReached = useCallback(() => {
    if (latched.current) return;
    latched.current = true;
    onReachedBottom?.();
  }, [onReachedBottom]);

  const handleScroll = useCallback(() => {
    if (latched.current) return;
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight <= SLACK_PX) {
      fireReached();
    }
  }, [fireReached]);

  // Keep the reading position stable across zoom changes: page height scales
  // linearly with `scale`, so the equivalent scroll offset is prev * ratio.
  const pendingScrollTop = useRef<number | null>(null);
  const zoomTo = useCallback((compute: (prev: number) => number) => {
    setScale((prev) => {
      const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, compute(prev)));
      if (next !== prev && scrollRef.current) {
        pendingScrollTop.current = (scrollRef.current.scrollTop * next) / prev;
      }
      return next;
    });
  }, []);

  useLayoutEffect(() => {
    if (pendingScrollTop.current === null) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = pendingScrollTop.current;
    pendingScrollTop.current = null;
  }, [scale]);

  const handleLoadSuccess = useCallback(
    ({ numPages: n }: { numPages: number }) => {
      setNumPages(n);
      setRenderedCount(0);
      setLoadError(null);
    },
    [],
  );

  const handlePageRenderSuccess = useCallback(() => {
    setRenderedCount((c) => c + 1);
  }, []);

  // Pdf.js renders each <Page> to canvas asynchronously after onLoadSuccess
  // fires. Checking the fits-without-scrolling condition immediately would
  // race against canvas painting and could auto-latch on an empty container.
  // Wait until every page has reported render success, then check on the
  // next frame so layout has settled.
  //
  // Only auto-latch at the default scale: a zoomed-out document that "fits"
  // would otherwise unlock the reading gate without the content ever being
  // legible.
  useEffect(() => {
    if (scale !== DEFAULT_SCALE) return;
    if (numPages === null || renderedCount < numPages) return;
    const el = scrollRef.current;
    if (!el) return;
    const id = requestAnimationFrame(() => {
      const cur = scrollRef.current;
      if (!cur) return;
      if (cur.scrollHeight <= cur.clientHeight + SLACK_PX) {
        fireReached();
      }
    });
    return () => cancelAnimationFrame(id);
  }, [numPages, renderedCount, fireReached, scale]);

  const handleLoadError = useCallback(
    (err: Error) => {
      setLoadError(err);
      onLoadError?.(err);
    },
    [onLoadError],
  );

  const handleDownload = useCallback(() => {
    triggerFileDownload(url, downloadFilename || "document.pdf");
  }, [url, downloadFilename]);

  const handleOpenInNewTab = useCallback(() => {
    window.open(url, "_blank", "noopener");
  }, [url]);

  const labels = LABELS[locale];
  const isDocumentReady = numPages !== null;

  return (
    <div className="flex flex-col overflow-hidden rounded-lg border bg-white">
      {!loadError && (
        <div className="flex items-center justify-between gap-2 border-b bg-gray-50 px-2 py-1.5">
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              data-testid="pdf-zoom-out"
              title={labels.zoomOut}
              aria-label={labels.zoomOut}
              disabled={!isDocumentReady || scale <= MIN_SCALE}
              onClick={() => zoomTo((prev) => prev - SCALE_STEP)}
            >
              <ZoomOut className="h-4 w-4" />
            </Button>
            <span
              data-testid="pdf-zoom-level"
              className="w-12 text-center text-xs font-medium tabular-nums text-gray-600"
            >
              {Math.round(scale * 100)}%
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              data-testid="pdf-zoom-in"
              title={labels.zoomIn}
              aria-label={labels.zoomIn}
              disabled={!isDocumentReady || scale >= MAX_SCALE}
              onClick={() => zoomTo((prev) => prev + SCALE_STEP)}
            >
              <ZoomIn className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              data-testid="pdf-zoom-reset"
              title={labels.resetZoom}
              aria-label={labels.resetZoom}
              disabled={!isDocumentReady || scale === DEFAULT_SCALE}
              onClick={() => zoomTo(() => DEFAULT_SCALE)}
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              data-testid="pdf-open-new-tab"
              title={labels.openInNewTab}
              aria-label={labels.openInNewTab}
              onClick={handleOpenInNewTab}
            >
              <ExternalLink className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              data-testid="pdf-download"
              title={labels.download}
              aria-label={labels.download}
              onClick={handleDownload}
            >
              <Download className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
      <div
        ref={scrollRef}
        data-testid="pdf-scroll-container"
        onScroll={handleScroll}
        className={`overflow-auto bg-white ${className ?? ""}`}
      >
        {loadError ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
            <AlertCircle className="h-8 w-8 text-red-500" />
            <p className="text-sm font-medium text-red-700">{labels.error}</p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setLoadError(null);
                setNumPages(null);
                setReloadToken((t) => t + 1);
              }}
            >
              <RotateCcw className="mr-1.5 h-4 w-4" />
              {labels.reload}
            </Button>
          </div>
        ) : (
          <Document
            key={`${url}#${reloadToken}`}
            file={url}
            loading={
              <div className="space-y-3 p-6">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-[90%]" />
                <Skeleton className="h-6 w-[85%]" />
                <Skeleton className="h-6 w-[95%]" />
                <p className="pt-2 text-center text-xs text-muted-foreground">
                  {labels.loading}
                </p>
              </div>
            }
            onLoadSuccess={handleLoadSuccess}
            onLoadError={handleLoadError}
          >
            {numPages !== null
              ? Array.from({ length: numPages }, (_, i) => (
                  <Page
                    key={i + 1}
                    pageNumber={i + 1}
                    scale={scale}
                    renderAnnotationLayer
                    renderTextLayer
                    onRenderSuccess={handlePageRenderSuccess}
                    className="mx-auto mb-2 w-fit"
                  />
                ))
              : null}
          </Document>
        )}
      </div>
    </div>
  );
}
