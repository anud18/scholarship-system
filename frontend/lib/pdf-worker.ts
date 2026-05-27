// Configures the pdf.js worker for react-pdf. Imported once by
// InlinePdfViewer so the worker URL is set before any <Document> mounts.
//
// Turbopack does not resolve `new URL("pdfjs-dist/...", import.meta.url)`
// for npm package paths, so we serve the worker from /public instead. The
// `copy-pdf-worker` script (run via postinstall + predev + prebuild) copies
// pdfjs-dist/build/pdf.worker.min.mjs into public/.
import { pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
