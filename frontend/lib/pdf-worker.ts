// Configures the pdf.js worker for react-pdf. Imported once by
// InlinePdfViewer so the worker URL is set before any <Document> mounts.
import { pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();
