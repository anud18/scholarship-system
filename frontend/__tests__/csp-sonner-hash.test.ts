/**
 * Drift guard for the sonner CSP style hash (issue #1273).
 *
 * The production `style-src` is nonce-gated, and sonner injects its stylesheet
 * imperatively with no nonce hook (see lib/security-headers.ts). The only way to
 * allow it is a content hash — which silently goes stale on every sonner upgrade,
 * and the failure mode is invisible in dev (the dev CSP still carries
 * 'unsafe-inline'): toasts simply lose ALL styling in production.
 *
 * This test recomputes the hash from the INSTALLED sonner bundle so an upgrade
 * fails CI loudly, with the replacement value printed in the diff.
 */
import { createHash } from "crypto";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { SONNER_EMPTY_STYLE_HASH, SONNER_STYLE_HASH } from "@/lib/security-headers";

function sha256Csp(content: string): string {
  return `'sha256-${createHash("sha256").update(content, "utf8").digest("base64")}'`;
}

describe("sonner CSP style hash", () => {
  it("matches the CSS in the installed sonner bundle", () => {
    // Read the file directly rather than require.resolve(): sonner's package
    // "exports" map does not expose the dist path, and jest's resolver honours it.
    const bundlePath = join(process.cwd(), "node_modules/sonner/dist/index.mjs");
    expect(existsSync(bundlePath)).toBe(true);
    const bundle = readFileSync(bundlePath, "utf8");

    // sonner's injector is `function wt(n,{insertAt:e}={}){...}` called once with
    // the whole stylesheet as a template literal: wt(`:where(html[dir="ltr"])...`).
    // Match the call that carries the stylesheet, identified by its first selector
    // rather than by the (minifier-generated, unstable) function name.
    const match = bundle.match(/\(`(:where\(html\[dir="ltr"\][\s\S]*?)`\)/);
    expect(match).not.toBeNull();

    const css = match![1];
    expect(css.length).toBeGreaterThan(1000);
    expect(css).toContain("data-sonner-toaster");

    // If this fails after a sonner upgrade, copy the RECEIVED value into
    // lib/security-headers.ts (SONNER_STYLE_HASH) — do NOT relax style-src.
    expect(sha256Csp(css)).toBe(SONNER_STYLE_HASH);
  });

  it("pins the empty-element hash sonner's two-step injection requires", () => {
    // sonner appends the <style> element BEFORE filling it, so the browser
    // hash-checks an empty element first. This hash is content-independent.
    expect(sha256Csp("")).toBe(SONNER_EMPTY_STYLE_HASH);
  });
});
