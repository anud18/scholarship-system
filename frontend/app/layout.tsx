import type React from "react";
import type { Metadata, Viewport } from "next";
import "./globals.css";
import { SessionExpiredProvider } from "@/contexts/session-expired-context";
import { DebugPanelWrapper } from "@/components/debug-panel-wrapper";
import { AppProvider } from "@/components/providers/app-provider";
import { Toaster } from "@/components/ui/sonner";
import { getNonce } from "./NonceProvider";

export const metadata: Metadata = {
  title: "獎學金申請與簽核系統 | 國立陽明交通大學教務處",
  description:
    "國立陽明交通大學獎學金申請與簽核系統，提供學生獎學金申請、教師推薦、行政審核等完整流程管理",
  keywords: "獎學金, 申請, 審核, 陽明交通大學, NYCU, 教務處",
  authors: [{ name: "國立陽明交通大學教務處" }],
  robots: "noindex, nofollow", // 系統內部使用
  generator: "v0.dev",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/nycu-favicon.svg", type: "image/svg+xml" },
    ],
    shortcut: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/nycu-favicon.svg", type: "image/svg+xml" },
    ],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#1e40af",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const nonce = await getNonce();

  return (
    <html lang="zh-TW" className="scroll-smooth">
      {/* The nonce attribute is injected per-request by the CSP middleware
          (see NonceProvider). It's only available server-side, so React's
          hydration always sees a mismatch (server: real nonce, client: ""
          because the middleware never runs in the browser). The rendered
          HTML is correct; suppressHydrationWarning is React's standard
          escape hatch for SSR-only attributes like this. Resolves the
          remaining hydration warnings flagged in the Phase 1 audit. */}
      <head nonce={nonce} suppressHydrationWarning>
        {/* Next.js will automatically apply nonce to all injected scripts */}
      </head>
      <body className="antialiased" nonce={nonce} suppressHydrationWarning>
        <AppProvider>
          <SessionExpiredProvider>
            {children}
            <DebugPanelWrapper />
            <Toaster />
          </SessionExpiredProvider>
        </AppProvider>
      </body>
    </html>
  );
}
