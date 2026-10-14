// CI-only (copied to frontend/app/api/v1/preview/sample/route.ts by
// .github/workflows/safari-pdf-preview.yml, never shipped): serves the sample
// PDF from under /api/v1/preview/, the prefix middleware.ts relaxes to
// same-origin framing — i.e. it behaves like the real preview proxy.
import { readFile } from "node:fs/promises";
import path from "node:path";

export async function GET() {
  const bytes = await readFile(path.join(process.cwd(), "public", "sample.pdf"));
  return new Response(new Uint8Array(bytes), {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Length": String(bytes.byteLength),
      "Content-Disposition": 'inline; filename="sample.pdf"',
    },
  });
}
