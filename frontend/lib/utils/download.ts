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
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Trigger a browser download of an already-authenticated same-origin URL
 * (e.g. an /api/v1/preview/... proxy URL) via a transient anchor.
 *
 * Shared by FilePreviewDialog and InlinePdfViewer download buttons.
 */
export function triggerFileDownload(url: string, filename: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.target = "_blank";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
