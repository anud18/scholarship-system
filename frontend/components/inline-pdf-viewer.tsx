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
  type LucideIcon,
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
  // Tailwind classes sizing the WHOLE viewer (toolbar + scroll area), e.g.
  // `h-[min(745px,calc(90vh-200px))]`. Required in practice — the component
  // has no intrinsic height without one. The toolbar consumes its share from
  // this budget, so callers only need to account for their own chrome.
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
// Cap on scale × devicePixelRatio for the canvas backing store. Without it,
// an A4 page at MAX_SCALE on a DPR-2 display needs ~18M backing pixels,
// past mobile Safari's ~16.7M canvas ceiling — the page would paint blank.
// With the cap the worst case is ~(595·4)×(842·4) ≈ 8M pixels.
const MAX_RASTER_FACTOR = 4;

const LABELS = {
  zh: {
    loading: "載入中…",
    error: "無法載入文件",
    errorFallback: "您仍可使用上方按鈕下載檔案或在新視窗開啟",
    reload: "重新載入",
    zoomIn: "放大",
    zoomOut: "縮小",
    resetZoom: "重設縮放",
    zoomHint: "縮放低於 100% 時不計入閱讀進度",
    download: "下載",
    openInNewTab: "在新視窗開啟",
  },
  en: {
    loading: "Loading…",
    error: "Failed to load document",
    errorFallback:
      "You can still download the file or open it in a new tab from the toolbar",
    reload: "Reload",
    zoomIn: "Zoom in",
    zoomOut: "Zoom out",
    resetZoom: "Reset zoom",
    zoomHint: "Zoom below 100% does not count toward reading progress",
    download: "Download",
    openInNewTab: "Open in new tab",
  },
} as const;

function ToolbarIconButton({
  icon: Icon,
  label,
  testId,
  disabled,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  testId: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8"
      data-testid={testId}
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
    >
      <Icon className="h-4 w-4" />
    </Button>
  );
}

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
  const [reachedBottom, setReachedBottom] = useState(false);

  const latched = useRef(false);
  // True from a zoom click until every page has re-rendered at the new scale
  // (plus one frame). While settling, scroll events are ignored: the browser
  // clamps scrollTop when page canvases resize (react-pdf resizes them in a
  // passive effect, after our restore below) and dispatches scroll events
  // that would otherwise satisfy the bottom check without any real reading.
  const settling = useRef(false);
  const pendingScrollTop = useRef<number | null>(null);
  // Identity of the document instance currently loaded. The settle effect
  // only acts when this matches the docKey being rendered — otherwise, on a
  // url change, it could run with stale numPages/renderedCount in the same
  // commit that unmounts the old pages and latch against the collapsed
  // container before the new document loads.
  const docKey = `${url}#${reloadToken}`;
  const loadedDocKey = useRef<string | null>(null);

  useEffect(() => {
    latched.current = false;
    settling.current = false;
    pendingScrollTop.current = null;
    setScale(DEFAULT_SCALE);
    setReachedBottom(false);
    setNumPages(null);
    setRenderedCount(0);
    setLoadError(null);
  }, [url, reloadToken]);

  const fireReached = useCallback(() => {
    if (latched.current) return;
    latched.current = true;
    setReachedBottom(true);
    onReachedBottom?.();
  }, [onReachedBottom]);

  // Single latch path for both "scrolled to the bottom" and "document fits
  // without scrolling" (a fitting document has scrollTop 0 and satisfies the
  // same inequality). Refuses to latch while zoomed below 100% — shrunken
  // content is not legible reading — and while a zoom transition is settling.
  const tryLatchAtBottom = useCallback(() => {
    if (latched.current || settling.current) return;
    if (scale < DEFAULT_SCALE) return;
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight <= SLACK_PX) {
      fireReached();
    }
  }, [scale, fireReached]);

  const zoomTo = useCallback(
    (next: number) => {
      const clamped = Math.min(MAX_SCALE, Math.max(MIN_SCALE, next));
      if (clamped === scale) return;
      const el = scrollRef.current;
      if (el) {
        // Page height scales linearly with `scale`, so the equivalent scroll
        // offset is the previous one times the scale ratio.
        pendingScrollTop.current = (el.scrollTop * clamped) / scale;
      }
      settling.current = true;
      setRenderedCount(0);
      setScale(clamped);
    },
    [scale],
  );

  // Best-effort immediate restore so the viewport doesn't visibly jump. The
  // canvases still have their old sizes here (react-pdf resizes them in a
  // passive effect), so this write may be clamped; the settle effect below
  // re-applies the restore once the new-scale layout is final.
  useLayoutEffect(() => {
    if (pendingScrollTop.current === null) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = pendingScrollTop.current;
  }, [scale]);

  // Runs once all pages have rendered at the current scale (renderedCount is
  // reset both on document load and on every zoom change): re-apply the
  // scroll restore against the final layout, then end the settling window and
  // re-check the bottom/fits condition on the next frame — which also covers
  // the initial "short document fits without scrolling" auto-latch.
  useEffect(() => {
    if (loadedDocKey.current !== docKey) return;
    if (numPages === null || renderedCount < numPages) return;
    const el = scrollRef.current;
    if (el && pendingScrollTop.current !== null) {
      el.scrollTop = pendingScrollTop.current;
    }
    pendingScrollTop.current = null;
    const id = requestAnimationFrame(() => {
      settling.current = false;
      tryLatchAtBottom();
    });
    return () => cancelAnimationFrame(id);
  }, [numPages, renderedCount, tryLatchAtBottom, docKey]);

  const handleLoadSuccess = useCallback(
    ({ numPages: n }: { numPages: number }) => {
      loadedDocKey.current = docKey;
      setNumPages(n);
      setRenderedCount(0);
      setLoadError(null);
    },
    [docKey],
  );

  const handlePageRenderSuccess = useCallback(() => {
    setRenderedCount((c) => c + 1);
  }, []);

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
  const isDocumentReady = numPages !== null && !loadError;
  const devicePixelRatio =
    typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  const effectiveDpr = Math.min(devicePixelRatio, MAX_RASTER_FACTOR / scale);

  return (
    <div
      className={`flex flex-col overflow-hidden rounded-lg border bg-white ${className ?? ""}`}
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b bg-gray-50 px-2 py-1.5">
        <div className="flex items-center gap-1">
          <ToolbarIconButton
            icon={ZoomOut}
            label={labels.zoomOut}
            testId="pdf-zoom-out"
            disabled={!isDocumentReady || scale <= MIN_SCALE}
            onClick={() => zoomTo(scale - SCALE_STEP)}
          />
          <span
            data-testid="pdf-zoom-level"
            className="w-12 text-center text-xs font-medium tabular-nums text-gray-600"
          >
            {Math.round(scale * 100)}%
          </span>
          <ToolbarIconButton
            icon={ZoomIn}
            label={labels.zoomIn}
            testId="pdf-zoom-in"
            disabled={!isDocumentReady || scale >= MAX_SCALE}
            onClick={() => zoomTo(scale + SCALE_STEP)}
          />
          <ToolbarIconButton
            icon={RotateCcw}
            label={labels.resetZoom}
            testId="pdf-zoom-reset"
            disabled={!isDocumentReady || scale === DEFAULT_SCALE}
            onClick={() => zoomTo(DEFAULT_SCALE)}
          />
          {scale < DEFAULT_SCALE && !reachedBottom && (
            <span
              data-testid="pdf-zoom-hint"
              className="ml-1 text-xs text-amber-600"
            >
              {labels.zoomHint}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <ToolbarIconButton
            icon={ExternalLink}
            label={labels.openInNewTab}
            testId="pdf-open-new-tab"
            onClick={handleOpenInNewTab}
          />
          <ToolbarIconButton
            icon={Download}
            label={labels.download}
            testId="pdf-download"
            onClick={handleDownload}
          />
        </div>
      </div>
      <div
        ref={scrollRef}
        data-testid="pdf-scroll-container"
        onScroll={tryLatchAtBottom}
        className="min-h-0 flex-1 overflow-auto bg-white"
      >
        {loadError ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
            <AlertCircle className="h-8 w-8 text-red-500" />
            <p className="text-sm font-medium text-red-700">{labels.error}</p>
            <p className="text-xs text-muted-foreground">
              {labels.errorFallback}
            </p>
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
                    devicePixelRatio={effectiveDpr}
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
