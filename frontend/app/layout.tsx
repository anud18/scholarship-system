import type React from "react";
import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AuthProvider } from "@/hooks/use-auth";
import { NotificationProvider } from "@/contexts/notification-context";
import { SessionExpiredProvider } from "@/contexts/session-expired-context";
import { QueryProvider } from "@/components/providers/query-provider";
import { DebugPanelWrapper } from "@/components/debug-panel-wrapper";
import { SWRProvider } from "@/components/providers/swr-provider";

export const metadata: Metadata = {
  title: "獎學金申請與簽核系統 | 國立陽明交通大學教務處",
  description:
    "國立陽明交通大學獎學金申請與簽核系統，提供學生獎學金申請、教師推薦、行政審核等完整流程管理",
  keywords: "獎學金, 申請, 審核, 陽明交通大學, NYCU, 教務處",
  authors: [{ name: "國立陽明交通大學教務處" }],
  robots: "noindex, nofollow", // 系統內部使用
  generator: "v0.dev",
  themeColor: "#1e40af",
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
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW" className="scroll-smooth">
      <body className="antialiased">
        <QueryProvider>
          <SWRProvider>
            <AuthProvider>
              <NotificationProvider>
                <SessionExpiredProvider>
                  {children}
                  <DebugPanelWrapper />
                </SessionExpiredProvider>
              </NotificationProvider>
            </AuthProvider>
          </SWRProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
