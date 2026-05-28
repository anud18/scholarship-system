// Configures the pdf.js worker for react-pdf. Imported once by
// InlinePdfViewer so the worker URL is set before any <Document> mounts.
//
// Turbopack does not resolve `new URL("pdfjs-dist/...", import.meta.url)`
// for npm package paths, so we serve the worker from /public instead. The
// `copy-pdf-worker` script (run via postinstall + predev + prebuild) copies
// pdfjs-dist/build/pdf.worker.min.mjs into public/.
//
// The `?v=<pdfjs version>` query pins the worker URL to the bundled pdf.js
// version. Without it, a browser that once received a 404 HTML page for the
// bare /pdf.worker.min.mjs (e.g. a server started before the copy ran) keeps
// replaying that cached HTML even after the file exists — pdf.js then logs
// "Setting up fake worker" and fails with a module-MIME error. Bumping the
// query on every version makes the URL unique, so a stale cache can't stick.
import { pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = `/pdf.worker.min.mjs?v=${pdfjs.version}`;
