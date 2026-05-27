// Copies pdf.js worker from node_modules into public/ so Next.js serves it
// at /pdf.worker.min.mjs. Turbopack doesn't resolve `new URL(spec,
// import.meta.url)` for npm package paths, so we ship the worker via the
// static asset pipeline instead.
//
// Runs from package.json on postinstall, predev, and prebuild. Idempotent.
import { copyFileSync, mkdirSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname } from "node:path";

const require = createRequire(import.meta.url);
const src = require.resolve("pdfjs-dist/build/pdf.worker.min.mjs");
const dest = "public/pdf.worker.min.mjs";

mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);

if (!existsSync(dest)) {
  console.error(`copy-pdf-worker: dest ${dest} missing after copy`);
  process.exit(1);
}
console.log(`copy-pdf-worker: ${src} -> ${dest}`);
