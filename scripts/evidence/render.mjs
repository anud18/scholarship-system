#!/usr/bin/env node
// scripts/evidence/render.mjs — Renders a single index.html gallery for a
// docs/staging-tests/<date>/ tree.
//
// Usage:
//   node scripts/evidence/render.mjs --date 2026-05-07 [--src docs/staging-tests/2026-05-07] [--out .] [--inline]
//
// Layout assumed (per existing convention on audit/monitoring-stack-phase1):
//   <date>/
//     REPORT.md                  (executive summary; rendered at top)
//     <NN-flow>/                  e.g., 01-student-flow, 03-ranking-page
//       *.png  *.json  *.txt  *.js   sequential-prefixed evidence files
//       REPORT.md                 (optional per-flow sub-report)
//
// `--inline` reads each PNG once and embeds as base64 (single-file artifact).
// Default mode references PNGs as sibling files (small index.html, browser-
// browseable on the orphan branch's GitHub tree view).

import { readFileSync, readdirSync, statSync, writeFileSync, existsSync } from "node:fs";
import { resolve, join, basename, extname, relative } from "node:path";
import { argv } from "node:process";

// ──────────────────────────────────────────────────────────────────────────
// Args
// ──────────────────────────────────────────────────────────────────────────
const args = Object.fromEntries(
  argv
    .slice(2)
    .reduce((acc, a, i, arr) => {
      if (a.startsWith("--")) acc.push([a.replace(/^--/, ""), arr[i + 1]?.startsWith("--") || arr[i + 1] === undefined ? true : arr[i + 1]]);
      return acc;
    }, [])
);

const date = args.date;
if (!date) {
  console.error("usage: render.mjs --date YYYY-MM-DD [--src DIR] [--out DIR] [--inline]");
  process.exit(2);
}
const srcDir = resolve(args.src || `docs/staging-tests/${date}`);
const outDir = resolve(args.out || ".");
const inline = Boolean(args.inline);

if (!existsSync(srcDir)) {
  console.error(`source directory not found: ${srcDir}`);
  process.exit(2);
}

// ──────────────────────────────────────────────────────────────────────────
// File walking
//
// Each "flow" is a directory that directly contains evidence files (PNG /
// JSON / TXT / JS). We walk recursively from srcDir and treat every dir
// with at least one such file as a flow. The flow's display name is the
// path relative to srcDir, so nested layouts like
//
//   2026-05-07/
//     local-validation-2day/agent-c-auth/...
//
// surface as flow `local-validation-2day/agent-c-auth`, preserving order.
// ──────────────────────────────────────────────────────────────────────────
function listDir(p) {
  return readdirSync(p)
    .map((name) => ({ name, full: join(p, name), stat: statSync(join(p, name)) }))
    .sort((a, b) => a.name.localeCompare(b.name, "en", { numeric: true }));
}

const EVIDENCE_EXTS = new Set([".png", ".json", ".txt", ".js"]);

function walkFlows(root) {
  const flows = [];
  function visit(dir) {
    const entries = listDir(dir);
    const files = entries.filter((e) => e.stat.isFile());
    const subdirs = entries.filter((e) => e.stat.isDirectory() && e.name !== ".git");
    const evidenceFiles = files.filter((f) => EVIDENCE_EXTS.has(extname(f.name).toLowerCase()));
    if (evidenceFiles.length > 0) {
      const rel = relative(root, dir) || ".";
      const subReportPath = join(dir, "REPORT.md");
      flows.push({
        name: rel,
        path: dir,
        subReport: existsSync(subReportPath) ? readFileSync(subReportPath, "utf8") : "",
        files: evidenceFiles,
      });
    }
    for (const sd of subdirs) visit(sd.full);
  }
  visit(root);
  flows.sort((a, b) => a.name.localeCompare(b.name, "en", { numeric: true }));
  return flows;
}

const topReportPath = join(srcDir, "REPORT.md");
const topReport = existsSync(topReportPath) ? readFileSync(topReportPath, "utf8") : "";

const flows = walkFlows(srcDir);

const stats = {
  flows: flows.length,
  png: flows.reduce((n, f) => n + f.files.filter((x) => x.name.endsWith(".png")).length, 0),
  json: flows.reduce((n, f) => n + f.files.filter((x) => x.name.endsWith(".json")).length, 0),
  txt: flows.reduce((n, f) => n + f.files.filter((x) => x.name.endsWith(".txt")).length, 0),
  js: flows.reduce((n, f) => n + f.files.filter((x) => x.name.endsWith(".js")).length, 0),
  bytes: flows.reduce(
    (n, f) => n + f.files.reduce((m, x) => m + x.stat.size, 0),
    0
  ),
};

// ──────────────────────────────────────────────────────────────────────────
// Rendering helpers
// ──────────────────────────────────────────────────────────────────────────
const escapeHtml = (s) =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

// Tiny markdown renderer — no SaaS dependency. Handles headings, paragraphs,
// fenced code, inline code, bold/italic, links, lists, tables. Good enough for
// the REPORT.md shape used in this repo.
function md(text) {
  if (!text) return "";
  const lines = text.split("\n");
  let out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    // fenced code
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        buf.push(lines[i]);
        i++;
      }
      i++;
      out.push(`<pre class="code"><code class="lang-${escapeHtml(lang)}">${escapeHtml(buf.join("\n"))}</code></pre>`);
      continue;
    }
    // table — header | sep | rows
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s\-:|]+\|\s*$/.test(lines[i + 1])) {
      const header = line.split("|").slice(1, -1).map((c) => c.trim());
      i += 2; // skip separator
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        rows.push(lines[i].split("|").slice(1, -1).map((c) => c.trim()));
        i++;
      }
      out.push(
        `<table><thead><tr>${header.map((h) => `<th>${inline2(h)}</th>`).join("")}</tr></thead><tbody>${rows
          .map((r) => `<tr>${r.map((c) => `<td>${inline2(c)}</td>`).join("")}</tr>`)
          .join("")}</tbody></table>`
      );
      continue;
    }
    // heading
    const h = /^(#{1,6})\s+(.*)$/.exec(line);
    if (h) {
      out.push(`<h${h[1].length}>${inline2(h[2])}</h${h[1].length}>`);
      i++;
      continue;
    }
    // unordered list
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      out.push(`<ul>${items.map((x) => `<li>${inline2(x)}</li>`).join("")}</ul>`);
      continue;
    }
    // blank
    if (line.trim() === "") {
      i++;
      continue;
    }
    // paragraph (collect contiguous non-blank lines)
    const buf = [line];
    i++;
    while (i < lines.length && lines[i].trim() !== "" && !/^[#`|-]/.test(lines[i].trim())) {
      buf.push(lines[i]);
      i++;
    }
    out.push(`<p>${inline2(buf.join(" "))}</p>`);
  }
  return out.join("\n");
}
function safeUrl(url) {
  const trimmed = url.trim();
  if (/^(javascript|data|vbscript|file):/i.test(trimmed)) return "#";
  return trimmed;
}
function inline2(s) {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>")
    .replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      (_m, text, url) =>
        `<a href="${safeUrl(url)}" target="_blank" rel="noopener">${text}</a>`,
    );
}

function readFileBlock(file) {
  const ext = extname(file.name).toLowerCase();
  if (ext === ".png") {
    if (inline) {
      const b64 = readFileSync(file.full).toString("base64");
      return `<img loading="lazy" src="data:image/png;base64,${b64}" alt="${escapeHtml(file.name)}">`;
    }
    const rel = relative(outDir, file.full);
    return `<img loading="lazy" src="${escapeHtml(rel)}" alt="${escapeHtml(file.name)}">`;
  }
  if (ext === ".json" || ext === ".txt" || ext === ".js") {
    const content = readFileSync(file.full, "utf8");
    const lang = ext === ".json" ? "json" : ext === ".js" ? "javascript" : "text";
    return `<details><summary>${escapeHtml(file.name)} <span class="size">(${formatSize(file.stat.size)})</span></summary><pre class="code"><code class="lang-${lang}">${escapeHtml(content)}</code></pre></details>`;
  }
  return `<div class="other">${escapeHtml(file.name)} (${formatSize(file.stat.size)})</div>`;
}

function formatSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
}

// ──────────────────────────────────────────────────────────────────────────
// HTML output
// ──────────────────────────────────────────────────────────────────────────
const html = `<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Staging evidence — ${escapeHtml(date)}</title>
  <style>
    :root { color-scheme: light dark; }
    body { font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
           margin: 0; padding: 0 24px 80px; max-width: 1100px; margin-inline: auto; }
    header { padding: 28px 0 12px; border-bottom: 1px solid #ddd; }
    header h1 { margin: 0 0 6px; font-size: 22px; }
    header .meta { color: #666; font-size: 13px; }
    nav.toc { position: sticky; top: 0; background: rgba(255,255,255,0.9); padding: 10px 0;
              border-bottom: 1px solid #eee; backdrop-filter: blur(6px); }
    @media (prefers-color-scheme: dark) {
      body { background: #0e0e0e; color: #e7e7e7; }
      header { border-color: #333; }
      header .meta { color: #999; }
      nav.toc { background: rgba(14,14,14,0.9); border-color: #333; }
    }
    nav.toc ol { display: flex; flex-wrap: wrap; gap: 8px 16px; padding-left: 0; list-style: none; margin: 0; }
    nav.toc a { text-decoration: none; }
    section.flow { margin: 32px 0; padding-top: 8px; }
    section.flow > h2 { margin: 0 0 8px; font-size: 17px; }
    .files { display: grid; grid-template-columns: 1fr; gap: 14px; }
    .file { padding: 12px; border: 1px solid #e3e3e3; border-radius: 8px; background: #fafafa; }
    @media (prefers-color-scheme: dark) {
      .file { border-color: #2a2a2a; background: #161616; }
    }
    .file > .name { font-weight: 600; margin-bottom: 6px; word-break: break-word; }
    .file img { max-width: 100%; height: auto; display: block; border: 1px solid #d0d0d0; border-radius: 4px; }
    @media (prefers-color-scheme: dark) {
      .file img { border-color: #333; }
    }
    .file .size { color: #888; font-weight: 400; font-size: 12px; }
    pre.code { margin: 8px 0 0; padding: 10px; background: #f4f4f4; border-radius: 6px;
               overflow-x: auto; font-size: 12px; line-height: 1.45; }
    @media (prefers-color-scheme: dark) {
      pre.code { background: #0a0a0a; }
    }
    table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
    table th, table td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; vertical-align: top; }
    @media (prefers-color-scheme: dark) {
      table th, table td { border-color: #333; }
    }
    details summary { cursor: pointer; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12.5px; }
    .summary { color: #666; font-size: 13px; padding: 6px 0 14px; }
    @media (prefers-color-scheme: dark) {
      .summary { color: #999; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Staging evidence — ${escapeHtml(date)}</h1>
    <div class="meta">${stats.flows} flows · ${stats.png} PNG · ${stats.json} JSON · ${stats.txt} TXT · ${stats.js} JS · ${formatSize(stats.bytes)} total</div>
  </header>

  <nav class="toc">
    <ol>
      ${flows.map((f, i) => `<li><a href="#${escapeHtml(f.name)}">${escapeHtml(f.name)}</a></li>`).join("")}
    </ol>
  </nav>

  ${topReport ? `<section class="report">${md(topReport)}</section>` : ""}

  ${flows
    .map(
      (f) => `
    <section class="flow" id="${escapeHtml(f.name)}">
      <h2>${escapeHtml(f.name)}</h2>
      ${f.subReport ? `<div class="sub-report">${md(f.subReport)}</div>` : ""}
      <div class="files">
        ${f.files
          .filter((x) => x.name !== "REPORT.md")
          .map(
            (x) => `<div class="file"><div class="name">${escapeHtml(x.name)} <span class="size">(${formatSize(x.stat.size)})</span></div>${readFileBlock(x)}</div>`
          )
          .join("")}
      </div>
    </section>`
    )
    .join("")}

  <footer class="summary">
    Generated by <code>scripts/evidence/render.mjs</code> · mode: ${inline ? "inline (self-contained)" : "external (sibling assets)"}
  </footer>
</body>
</html>
`;

const outPath = join(outDir, "index.html");
writeFileSync(outPath, html, "utf8");
console.error(
  `wrote ${outPath} — ${stats.flows} flows, ${stats.png + stats.json + stats.txt + stats.js} files, ${formatSize(stats.bytes)} input`
);
