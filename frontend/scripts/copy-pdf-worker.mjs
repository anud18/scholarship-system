// Copies pdf.js worker from node_modules into public/ so Next.js serves it
// at /pdf.worker.min.mjs. Turbopack doesn't resolve `new URL(spec,
// import.meta.url)` for npm package paths, so we ship the worker via the
// static asset pipeline instead.
//
// Runs from package.json on postinstall, predev, and prebuild. Idempotent.
import { readFileSync, writeFileSync, mkdirSync, existsSync, unlinkSync } from "node:fs";
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

const srcBytes = readFileSync(src);

// Skip the write when an identical copy already exists. A prior `docker compose
// up --build` (running as root) can leave a root-owned worker file in the
// bind-mounted public/ dir; a later host-side `npm install` postinstall runs as
// a non-root user and cannot overwrite it -> EACCES. The file it would write is
// byte-identical (same pdfjs-dist), so treat "already correct" as success.
if (existsSync(dest) && readFileSync(dest).equals(srcBytes)) {
  console.log(`copy-pdf-worker: ${dest} already up to date, skipping`);
  process.exit(0);
}

mkdirSync(dirname(dest), { recursive: true });
// Read-then-write instead of copyFileSync: the latter uses copy_file_range/
// fcopyfile, which returns EPERM when src and dest straddle a reflink/overlay
// boundary (e.g. cache-restored node_modules in CI). A userspace copy avoids it.
try {
  writeFileSync(dest, srcBytes);
} catch (err) {
  // A foreign-owned dest (e.g. root-owned from a docker build) blocks an
  // in-place overwrite. Unlink and recreate before giving up.
  if (err.code === "EACCES" || err.code === "EPERM") {
    try {
      unlinkSync(dest);
    } catch {
      // ignore; rethrow original if recreate still fails
    }
    writeFileSync(dest, srcBytes);
  } else {
    throw err;
  }
}

if (!existsSync(dest)) {
  console.error(`copy-pdf-worker: dest ${dest} missing after copy`);
  process.exit(1);
}
console.log(`copy-pdf-worker: ${src} -> ${dest}`);
