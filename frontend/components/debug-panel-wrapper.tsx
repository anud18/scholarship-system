"use client";

import dynamic from "next/dynamic";

/**
 * Client Component wrapper for DebugPanel with lazy loading
 *
 * This wrapper is necessary because:
 * - Next.js App Router requires "use client" for dynamic imports with ssr: false
 * - Allows DebugPanel to be lazy-loaded and tree-shaken in production
 * - Environment check ensures zero overhead when disabled
 */

// Lazy load DebugPanel only when enabled (tree-shaken in production)
const DebugPanel = dynamic(
  () => import("./debug-panel").then((m) => ({ default: m.DebugPanel })),
  {
    ssr: false,
    loading: () => null,
  }
);

export function DebugPanelWrapper() {
  // Only render if explicitly enabled via environment variable
  if (process.env.NEXT_PUBLIC_ENABLE_DEBUG_PANEL !== "true") {
    return null;
  }

  return <DebugPanel />;
}
