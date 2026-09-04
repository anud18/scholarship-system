import { previewMimeType } from "@/lib/utils";
import {
  buildSecurePreviewUrl,
  getAuthToken,
} from "@/lib/utils/url-validation";

/** The subset of ApplicationDocument the example-file preview needs. */
export interface ExampleDocumentSource {
  id: number;
  document_name: string;
  example_file_url?: string | null;
}

/** Shape consumed by FilePreviewDialog's `file` prop. */
export interface ExampleDocumentPreview {
  url: string;
  filename: string;
  type: string;
}

const EXAMPLE_SUFFIX = "_example";

/**
 * Mirror the filename the backend puts in Content-Disposition for
 * GET /application-fields/documents/{id}/example:
 * `<document_name>_example.<ext>` (always the zh document_name), so the dialog
 * caption matches what the browser actually saves on 下載.
 */
export function exampleDocumentFilename(doc: ExampleDocumentSource): string {
  const objectName = (doc.example_file_url ?? "").split("/").pop() ?? "";
  const dotIndex = objectName.lastIndexOf(".");
  const extension =
    dotIndex > 0 ? objectName.slice(dotIndex + 1).toLowerCase() : "";
  const base = `${doc.document_name}${EXAMPLE_SUFFIX}`;
  return extension ? `${base}.${extension}` : base;
}

/**
 * Build the FilePreviewDialog descriptor for an admin-uploaded example file.
 * Returns null when the document has no example. Throws if the secure URL
 * builder rejects the endpoint (never expected for the hardcoded path).
 *
 * Shared by the student application form (查看範例文件) and the admin
 * scholarship management page (預覽範例) so both stay in lockstep.
 */
export function buildExampleDocumentPreview(
  doc: ExampleDocumentSource
): ExampleDocumentPreview | null {
  if (!doc.example_file_url) return null;

  // SECURITY: Use validated URL builder to prevent open redirect
  const url = buildSecurePreviewUrl("/api/v1/preview/examples", {
    documentId: doc.id,
    token: getAuthToken(),
  });
  const filename = exampleDocumentFilename(doc);

  return { url, filename, type: previewMimeType(filename) };
}
