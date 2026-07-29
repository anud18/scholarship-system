/**
 * Response security-header values shared by the Next.js middleware and the nginx
 * configs (nginx/nginx.prod.conf, nginx/nginx.staging.conf).
 *
 * Issue #1223 section B (OWASP ZAP baseline hardening).
 *
 * WHY BOTH LAYERS: the repo already duplicates X-Frame-Options /
 * X-Content-Type-Options / Referrer-Policy across middleware.ts and nginx
 * ("defense in depth", middleware.ts). nginx-only would leave localhost dev and
 * any non-nginx path uncovered; middleware-only would leave the nginx-served
 * paths that Next.js never sees (e.g. `/_next/static/`) uncovered.
 *
 * WHY THE VALUES MUST BE BYTE-IDENTICAL: nginx `add_header` APPENDS to the
 * upstream (Next.js) response, so a page served through nginx carries these
 * headers TWICE. Permissions-Policy is an RFC 8941 Structured Dictionary —
 * duplicate field lines are comma-joined and duplicate keys are last-wins, so
 * two identical values are idempotent, but two DIVERGENT values silently union
 * with nginx (which appends last) winning every overlapping key.
 * `__tests__/security-headers-nginx-parity.test.ts` pins both layers to these
 * exact strings by reading the nginx configs.
 */

/**
 * Deny-by-default browser-feature policy.
 *
 * The app calls exactly ONE policy-controlled feature:
 *   - `clipboard-write` — `navigator.clipboard.writeText` in
 *     components/debug-panel.tsx (the floating debug widget, rendered from
 *     app/layout.tsx on localhost AND ss.test.nycu.edu.tw), plus Grafana's
 *     copy-link buttons behind the staging `^~ /monitoring` proxy, which
 *     inherits this header. `clipboard-write=()` WOULD break both, and because
 *     next.config.mjs strips console in production the failure would be silent.
 *
 * `components/ui/tags-input.tsx` reads `e.clipboardData` from a paste EVENT,
 * which is NOT gated by `clipboard-read` — so `clipboard-read` stays denied.
 *
 * `fullscreen` is not called today but is left at its `self` default so a future
 * PDF/image viewer cannot be broken by this header.
 *
 * NOTE the classic syntax bug: inside Permissions-Policy the origin keyword is a
 * BARE token `self`, NOT CSP's quoted `'self'`. `clipboard-write=('self')` is
 * invalid and the whole entry is silently dropped.
 *
 * Deliberately NOT listed, both for the same reason — Chromium does not
 * recognise the token, so it grants no protection and only logs
 * "Unrecognized feature" on every page load:
 *   - `interest-cohort` (FLoC was removed from Chrome; its successor
 *     `browsing-topics` IS listed and denied)
 *   - `bluetooth` (verified empirically against this exact header: of the 24
 *     tokens below Chromium accepts all of them, and rejected `bluetooth`)
 * Nothing in the app uses Web Bluetooth, so dropping it costs no coverage.
 *
 * Legacy `Feature-Policy` is deliberately NOT emitted: Chrome renamed the header
 * in v88 and no longer honours it, and Firefox/Safari never shipped it at all.
 * It would buy zero coverage and create a second string to drift out of sync.
 */
export const PERMISSIONS_POLICY = [
  "accelerometer=()",
  "autoplay=()",
  "browsing-topics=()",
  "camera=()",
  "clipboard-read=()",
  "clipboard-write=(self)",
  "display-capture=()",
  "encrypted-media=()",
  "fullscreen=(self)",
  "geolocation=()",
  "gyroscope=()",
  "hid=()",
  "idle-detection=()",
  "local-fonts=()",
  "magnetometer=()",
  "microphone=()",
  "midi=()",
  "payment=()",
  "picture-in-picture=()",
  "publickey-credentials-get=()",
  "screen-wake-lock=()",
  "serial=()",
  "usb=()",
  "xr-spatial-tracking=()",
].join(", ");

/**
 * Severs `window.opener` between this app and cross-origin documents (XS-Leaks /
 * tabnabbing defence).
 *
 * `same-origin-allow-popups` rather than the stricter `same-origin` because
 * components/react-email-template-viewer.tsx opens `window.open("", "_blank")`
 * and then writes into `sourceWindow.document` — the admin "view email template
 * source" flow. Per spec an about:blank popup inherits its opener's COOP and
 * stays in the same browsing-context group, so `same-origin` *should* also work,
 * but `-allow-popups` makes that flow correct by construction while still
 * blocking every cross-origin document from retaining a handle on us.
 *
 * NYCU Portal SSO is unaffected either way: both legs are top-level redirects
 * (components/sso-login-page.tsx -> Portal form POST -> backend RedirectResponse
 * -> /auth/sso-callback?token=), never a popup with an opener callback.
 */
export const CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups";

/**
 * Blocks foreign origins from embedding our responses as no-cors subresources
 * (`<img>`, `<script>`, `<link>`), the Spectre-era side-channel defence.
 *
 * Safe for the file-preview chain: CORP governs no-cors SUBRESOURCE fetches, not
 * iframe navigations, so the same-origin `/api/v1/preview*` iframes are outside
 * its scope entirely.
 *
 * Cross-Origin-Embedder-Policy is deliberately NOT set — see the note in
 * middleware.ts. COEP `require-corp` would demand a CORP header on every
 * subresource the preview iframes pull, and buys nothing here because the app
 * uses no SharedArrayBuffer and never needs `crossOriginIsolated`.
 */
export const CROSS_ORIGIN_RESOURCE_POLICY = "same-origin";
