// Copies pdf.js worker from node_modules into public/ so Next.js serves it
// at /pdf.worker.min.mjs. Turbopack doesn't resolve `new URL(spec,
// import.meta.url)` for npm package paths, so we ship the worker via the
// static asset pipeline instead.
//
// Runs from package.json on postinstall, predev, and prebuild. Idempotent.
import { copyFileSync, mkdirSync, existsSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// Anchor require.resolve to the frontend package root so it finds
// node_modules even when invoked from a different cwd.
const require = createRequire(resolve(here, "..", "package.json"));
const src = require.resolve("pdfjs-dist/build/pdf.worker.min.mjs");
// Resolve dest relative to the script's own location (frontend/scripts/),
// so the script works no matter what cwd it was invoked from.
const dest = resolve(here, "..", "public", "pdf.worker.min.mjs");

mkdirSync(dirname(dest), { recursive: true });
// Remove any pre-existing copy before writing. On self-hosted CI runners the
// dev docker container (running as root) can create this file via its predev
// hook, leaving a root-owned file that a later host-side `npm install`
// postinstall (running as the runner user) cannot overwrite -> EPERM on
// copyFileSync. Unlinking only needs write permission on public/ (owned by the
// checkout), so it succeeds regardless of the stale file's owner.
rmSync(dest, { force: true });
copyFileSync(src, dest);

if (!existsSync(dest)) {
  console.error(`copy-pdf-worker: dest ${dest} missing after copy`);
  process.exit(1);
}
console.log(`copy-pdf-worker: ${src} -> ${dest}`);
