/** Click a transient anchor to hand a download off to the browser. */
function downloadViaAnchor({
  href,
  filename,
  target,
}: {
  href: string;
  filename: string;
  target?: string;
}): void {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  if (target) {
    link.target = target;
    link.rel = "noopener noreferrer";
  }
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

/**
 * Trigger a browser download for a fetched binary export.
 *
 * Shared by the college ranking export/template handlers and the distribution
 * results export, which all receive { blob, filename } from the college API module.
 */
export function triggerBlobDownload({
  blob,
  filename,
}: {
  blob: Blob;
  filename: string;
}): void {
  const url = URL.createObjectURL(blob);
  downloadViaAnchor({ href: url, filename });
  URL.revokeObjectURL(url);
}

/**
 * Trigger a browser download of an already-authenticated SAME-ORIGIN URL
 * (e.g. an /api/v1/preview/... proxy URL). The `download` attribute is only
 * honored same-origin; do not pass cross-origin URLs — they would open in a
 * tab instead of downloading.
 *
 * Shared by FilePreviewDialog and InlinePdfViewer download buttons.
 */
export function triggerFileDownload(url: string, filename: string): void {
  downloadViaAnchor({ href: url, filename, target: "_blank" });
}
