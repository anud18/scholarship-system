"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, Eye, FileText } from "lucide-react";
import { Locale } from "@/lib/validators";
import { getTranslation } from "@/lib/i18n";
import { isLocalObjectUrl } from "@/lib/file-preview";
import { triggerFileDownload } from "@/lib/utils/download";
import { logger } from "@/lib/utils/logger";

// pdf.js is heavy and only needed for a just-picked local PDF: keep it out of
// the initial chunk (see frontend/CLAUDE.md, "Lazy-load heavy frontend libs").
const InlinePdfViewer = dynamic(
  () => import("@/components/inline-pdf-viewer").then(m => m.InlinePdfViewer),
  { ssr: false }
);

interface FilePreviewDialogProps {
  isOpen: boolean;
  onClose: () => void;
  file: {
    url: string;
    filename: string;
    type: string;
    downloadUrl?: string; // 添加下載URL
    // The in-memory file behind a `blob:` `url` (a just-picked local file).
    // Required to preview a local PDF — see the note on the effect below.
    blob?: Blob;
  } | null;
  locale: Locale;
}

export function FilePreviewDialog({
  isOpen,
  onClose,
  file,
  locale,
}: FilePreviewDialogProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Image source: a fetched (or caller-owned local) blob: URL.
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  // Remote PDF source: the same-origin proxy URL to frame, once probed OK.
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const t = (k: string) => getTranslation(locale, k);

  const isPdf = !!file && file.type.includes("pdf");
  const isRenderable = !!file && (isPdf || file.type.includes("image"));
  // A local PDF is drawn from its Blob; without one there is nothing safe to
  // show (the effect below reports it), so never mount the viewer for it —
  // it would fall back to fetching the blob: URL, which the CSP refuses.
  const canDrawLocalPdf =
    isPdf && !!file && isLocalObjectUrl(file.url) && !!file.blob;

  // Get the viewer a source it can actually show.
  //
  // A remote file (a same-origin /api/v1/preview proxy URL) is fetched first:
  // pointing an <iframe>/<img> straight at the proxy cannot surface HTTP
  // errors — a 401 (expired token) or 404 (example deleted) body does not fire
  // onError, so the student saw the right caption over a blank pane. An image
  // then renders from the fetched blob. A PDF must NOT be re-wrapped in a blob
  // and framed: a `blob:` document inherits the page's CSP, and Safari applies
  // the inherited `frame-ancestors 'none'` against the blob's own parent, so
  // the frame stays blank (#1434). The fetch is only a status probe; the frame
  // then loads the proxy URL itself, which /api/v1/preview allows same-origin.
  //
  // A `blob:` URL is already local: the caller (FileUpload, for a file the
  // student just selected and has not saved yet) created it with
  // URL.createObjectURL and owns its lifetime. It cannot produce an HTTP
  // error, and fetching it is refused by the CSP (`connect-src` deliberately
  // lists no `blob:`; only frame-src/img-src do) — that refusal surfaced as
  // 「無法載入文件」 for every not-yet-saved upload. An image uses it as-is; a
  // PDF is drawn by pdf.js from `file.blob`, since the frame is not an option.
  // Neither path revokes the caller's URL.
  useEffect(() => {
    if (!isOpen || !file) return;

    setIsLoading(true);
    setLoadError(null);
    setObjectUrl(null);
    setFrameUrl(null);
    if (!isRenderable) {
      setIsLoading(false);
      return;
    }
    if (isLocalObjectUrl(file.url)) {
      if (!isPdf) {
        setObjectUrl(file.url);
        return;
      }
      setIsLoading(false);
      if (!file.blob) {
        logger.error("Local PDF preview needs the file's Blob", {
          url: file.url,
        });
        setLoadError(t("dialogs.preview.load_failed"));
      }
      return;
    }

    let isCancelled = false;
    let createdUrl: string | null = null;

    fetch(file.url, { credentials: "same-origin" })
      .then(async response => {
        if (!response.ok) {
          throw new Error(
            `Preview request failed with HTTP ${response.status}`
          );
        }
        if (isPdf) {
          // Only the status matters here: stop the browser receiving the body
          // (the proxy still serves it, so the frame's own request below is a
          // second full round trip — the price of not framing a blob:).
          await response.body?.cancel();
          if (isCancelled) return;
          setFrameUrl(file.url);
          return;
        }
        const blob = await response.blob();
        if (isCancelled) return;
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl(createdUrl);
      })
      .catch((error: unknown) => {
        if (isCancelled) return;
        logger.error("File preview failed to load", { url: file.url, error });
        setLoadError(t("dialogs.preview.load_failed"));
        setIsLoading(false);
      });

    return () => {
      isCancelled = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, file?.url, file?.type, file?.blob]);

  // The skeleton overlay is gated on `isLoading`, which is otherwise only
  // cleared by the viewer's onLoad/onError. That is reliable for images, but
  // Chrome's built-in PDF viewer frequently NEVER fires the iframe load event,
  // which left the skeleton covering an opacity-0 iframe forever. Fall back to
  // clearing the loading state on a short timer once the source is ready.
  const viewerSource = objectUrl ?? frameUrl;
  useEffect(() => {
    if (!viewerSource) return;
    const fallback = setTimeout(() => setIsLoading(false), 1500);
    return () => clearTimeout(fallback);
  }, [viewerSource]);

  const handleOpenInNewWindow = () => {
    if (!file) return;
    // The proxy URL carries the auth token: never leak window.opener/referrer.
    window.open(file.url, "_blank", "noopener,noreferrer");
  };

  const handleDownload = () => {
    if (!file) return;

    // 如果有專門的下載URL，使用它；否則使用預覽URL
    triggerFileDownload(file.downloadUrl || file.url, file.filename);
  };

  if (!file) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>{t("dialogs.preview.title")}</DialogTitle>
          <DialogDescription>{file.filename}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-hidden relative">
          {loadError ? (
            <div
              role="alert"
              className="flex flex-col items-center justify-center h-[70vh] bg-muted rounded"
            >
              <AlertCircle className="h-16 w-16 text-destructive mb-4" />
              <p className="text-lg font-medium mb-2">{file.filename}</p>
              <p className="text-sm text-muted-foreground">{loadError}</p>
            </div>
          ) : canDrawLocalPdf ? (
            <InlinePdfViewer
              url={file.url}
              blob={file.blob}
              downloadFilename={file.filename}
              locale={locale}
              hideActions
              className="h-[70vh]"
            />
          ) : isPdf ? (
            <>
              {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-background p-8">
                  <div className="w-full max-w-2xl space-y-4">
                    <div className="space-y-3">
                      <Skeleton className="h-6 w-full" />
                      <Skeleton className="h-6 w-[90%]" />
                      <Skeleton className="h-6 w-[85%]" />
                      <Skeleton className="h-6 w-[95%]" />
                      <Skeleton className="h-6 w-[80%]" />
                    </div>
                    <div className="space-y-3 pt-4">
                      <Skeleton className="h-6 w-full" />
                      <Skeleton className="h-6 w-[88%]" />
                      <Skeleton className="h-6 w-[92%]" />
                    </div>
                    <p className="text-sm text-muted-foreground text-center pt-4">
                      {t("dialogs.preview.loading")}
                    </p>
                  </div>
                </div>
              )}
              <iframe
                src={frameUrl ?? "about:blank"}
                data-source-url={file.url}
                className={`w-full h-[70vh] border rounded transition-opacity duration-300 ${
                  isLoading ? "opacity-0" : "opacity-100"
                }`}
                title={file.filename}
                onLoad={() => setIsLoading(false)}
                onError={() => setIsLoading(false)}
              />
            </>
          ) : file.type.includes("image") ? (
            <div className="flex justify-center items-center h-[70vh] bg-muted rounded relative">
              {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center p-8">
                  <Skeleton className="w-full h-full max-w-3xl max-h-[60vh] rounded-lg" />
                </div>
              )}
              {objectUrl && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={objectUrl}
                  alt={file.filename}
                  className={`max-w-full max-h-full object-contain transition-opacity duration-300 ${
                    isLoading ? "opacity-0" : "opacity-100"
                  }`}
                  onLoad={() => setIsLoading(false)}
                  onError={() => setIsLoading(false)}
                />
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-[70vh] bg-muted rounded">
              <FileText className="h-16 w-16 text-muted-foreground mb-4" />
              <p className="text-lg font-medium mb-2">{file.filename}</p>
              <p className="text-sm text-muted-foreground mb-4">
                {t("dialogs.preview.cannot_preview")}
              </p>
              <Button onClick={handleOpenInNewWindow} variant="outline">
                <Eye className="h-4 w-4 mr-2" />
                {t("dialogs.preview.open_in_new_window")}
              </Button>
            </div>
          )}

          <div className="flex justify-between items-center mt-4">
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleOpenInNewWindow}>
                <Eye className="h-4 w-4 mr-2" />
                {t("dialogs.preview.open_in_new_window")}
              </Button>
              <Button variant="outline" onClick={handleDownload}>
                <FileText className="h-4 w-4 mr-2" />
                {t("dialogs.preview.download")}
              </Button>
            </div>
            <Button variant="outline" onClick={onClose}>
              {t("dialogs.preview.close")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
