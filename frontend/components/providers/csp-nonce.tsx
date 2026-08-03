"use client";

import { createContext, useContext } from "react";

/**
 * Client-side plumbing for the per-request CSP nonce. Issue #1273.
 *
 * With production `style-src` nonce-gated (no 'unsafe-inline'), EVERY <style>
 * element that reaches the DOM needs the nonce. Three different mechanisms need
 * it, and they each take it from a different place:
 *
 *  1. `__webpack_nonce__` — read by `get-nonce`, which `react-style-singleton`
 *     (via `react-remove-scroll`, used by every Radix scroll-locking primitive:
 *     Select, DropdownMenu, Dialog, Popover) uses to stamp its injected
 *     `.with-scroll-bars-hidden` stylesheet. Setting the webpack runtime nonce
 *     is the ONLY hook those packages expose.
 *  2. `useCspNonce()` — Radix components that render their own `<style>` in JSX
 *     and accept a `nonce` prop: `Select.Viewport`, `ScrollArea.Viewport`.
 *     See components/ui/select.tsx and components/ui/scroll-area.tsx.
 *  3. Hashes in the CSP itself — for libraries with no nonce hook at all
 *     (sonner). See lib/security-headers.ts.
 *
 * The nonce originates in middleware.ts, travels on the `x-nonce` REQUEST header,
 * and is read by app/layout.tsx (getNonce) which renders this provider.
 */

const CspNonceContext = createContext<string | undefined>(undefined);

declare let __webpack_nonce__: string;

export function CspNonceProvider({
  nonce,
  children,
}: {
  nonce?: string;
  children: React.ReactNode;
}) {
  if (nonce) {
    // webpack rewrites this identifier to `__webpack_require__.nc`, which its
    // runtime stamps onto every style/script element it injects. Assigned during
    // render (not in an effect) so it is set before any child mounts a portal.
    //
    // The try/catch is NOT defensive padding: outside a webpack bundle the
    // identifier is undeclared, and ES module code is strict-mode, so the bare
    // assignment throws ReferenceError and takes the whole tree down. That is
    // every non-webpack runtime — jest (caught by __tests__/csp-nonce-wiring)
    // and Turbopack `next dev`. Only the production webpack build needs it, and
    // only production has a nonce-gated style-src.
    try {
      __webpack_nonce__ = nonce;
    } catch {
      /* not a webpack runtime — nothing to publish the nonce to */
    }
  }
  return <CspNonceContext.Provider value={nonce}>{children}</CspNonceContext.Provider>;
}

/**
 * The active CSP nonce, or undefined when rendered outside the provider.
 * Pass to any Radix primitive that renders its own <style> (see above).
 */
export function useCspNonce(): string | undefined {
  return useContext(CspNonceContext);
}
