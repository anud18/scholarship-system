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
