"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page } from "react-pdf";
import { AlertCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// Side-effect import: configures pdfjs.GlobalWorkerOptions.workerSrc.
import "@/lib/pdf-worker";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

interface InlinePdfViewerProps {
  url: string;
  // Fixed pixel height. Use `className` instead for responsive sizing
  // (e.g. `h-[min(700px,calc(90vh-200px))]`).
  height?: number;
  className?: string;
  onReachedBottom?: () => void;
  onLoadError?: (err: Error) => void;
  locale?: "zh" | "en";
}

const SLACK_PX = 8;

export function InlinePdfViewer({
  url,
  height,
  className,
  onReachedBottom,
  onLoadError,
  locale = "zh",
}: InlinePdfViewerProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [renderedCount, setRenderedCount] = useState(0);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

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
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight <= SLACK_PX) {
      fireReached();
    }
  }, [fireReached]);

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
  useEffect(() => {
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
  }, [numPages, renderedCount, fireReached]);

  const handleLoadError = useCallback(
    (err: Error) => {
      setLoadError(err);
      onLoadError?.(err);
    },
    [onLoadError],
  );

  const labels =
    locale === "zh"
      ? { loading: "載入中…", error: "無法載入文件", reload: "重新載入" }
      : { loading: "Loading…", error: "Failed to load document", reload: "Reload" };

  return (
    <div
      ref={scrollRef}
      data-testid="pdf-scroll-container"
      onScroll={handleScroll}
      className={`overflow-y-auto rounded-lg border bg-white ${className ?? ""}`}
      style={height !== undefined ? { height } : undefined}
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
                  renderAnnotationLayer
                  renderTextLayer
                  onRenderSuccess={handlePageRenderSuccess}
                  className="mx-auto mb-2"
                />
              ))
            : null}
        </Document>
      )}
    </div>
  );
}
