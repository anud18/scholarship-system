"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

/**
 * Client Component wrapper for DebugPanel with lazy loading
 *
 * This wrapper is necessary because:
 * - Next.js App Router requires "use client" for dynamic imports with ssr: false
 * - Allows DebugPanel to be lazy-loaded and tree-shaken in production
 * - Auto-detects test/staging environment by URL hostname
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
  const [shouldShow, setShouldShow] = useState(false);

  useEffect(() => {
    // Show debug panel if:
    // 1. URL hostname contains "test" (e.g., ss.test.nycu.edu.tw)
    // 2. Running on localhost (development)
    const hostname = window.location.hostname;
    const isTestEnvironment = hostname.includes("test");
    const isDevelopment = hostname === "localhost" || hostname === "127.0.0.1";

    setShouldShow(isTestEnvironment || isDevelopment);
  }, []);

  if (!shouldShow) {
    return null;
  }

  return <DebugPanel />;
}
