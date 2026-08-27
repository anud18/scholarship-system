"use client";

import { useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { GraduationCap, ExternalLink, LogOut, AlertTriangle } from "lucide-react";

// NYCU Portal SSO entry for the current environment. The Portal maps the app ID
// to our callback (/api/v1/auth/portal-sso/verify) and POSTs the SSO JWT there.
// Production uses the "esas" ID assigned by the IT center ("scholarship" belongs
// to another system on the production Portal); the test Portal still uses
// "scholarship".
const PRODUCTION_PORTAL = {
  url: "https://portal.nycu.edu.tw",
  appId: "esas",
} as const;
const TEST_PORTAL = {
  url: "https://portal.test.nycu.edu.tw",
  appId: "scholarship",
} as const;

function isTestEnvironment(): boolean {
  if (typeof window === "undefined") return false;
  const hostname = window.location.hostname;
  return (
    hostname.includes("test") ||
    hostname.includes("staging") ||
    hostname.includes("localhost") ||
    hostname === "140.113.7.148"
  );
}

function getPortalConfig() {
  return isTestEnvironment() ? TEST_PORTAL : PRODUCTION_PORTAL;
}

export function SSOLoginPage() {
  // Shown right after a real logout. The app session is cleared, but the NYCU
  // Portal SSO session (a host-only `userToken` cookie on portal.test) is NOT —
  // we can't clear it cross-origin and the Portal exposes no app-initiable
  // logout. So warn that the next login is one-click and offer a Portal logout.
  const [justLoggedOut, setJustLoggedOut] = useState(false);

  useEffect(() => {
    try {
      if (sessionStorage.getItem("nycu_portal_logout_notice") === "1") {
        setJustLoggedOut(true);
        sessionStorage.removeItem("nycu_portal_logout_notice");
      }
    } catch {
      // sessionStorage unavailable (private mode) — skip the notice.
    }
  }, []);

  const handleSSOLogin = () => {
    // Redirect to NYCU Portal for SSO authentication
    const portal = getPortalConfig();
    window.location.href = `${portal.url}/#/redirect/${portal.appId}`;
  };

  const handlePortalLogout = () => {
    // Open the NYCU Portal so the user can complete a full SSO logout there
    // (clicking the Portal's own LogOut clears the userToken cookie). We can't
    // do it for them: portal.test is a different host and exposes no logout URL.
    window.open(getPortalConfig().url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="nycu-gradient h-16 w-16 rounded-xl flex items-center justify-center nycu-shadow mx-auto mb-4">
            <GraduationCap className="h-8 w-8 text-white" />
          </div>
          <CardTitle className="text-2xl text-nycu-navy-800">登入系統</CardTitle>
          <CardDescription>博士生獎學金申請暨審核系統</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {justLoggedOut && (
              <div
                role="status"
                className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
              >
                <div className="flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-amber-600" />
                  <div className="space-y-2">
                    <p>
                      您已登出獎學金系統，但
                      <strong>NYCU Portal 仍保持登入</strong>
                      。在共用電腦上，下一位使用者可一鍵進入您的帳號。
                    </p>
                    <p className="text-amber-800">
                      如需完全登出，請至 NYCU Portal 點右上角頭像 →
                      <strong> 登出 (LogOut)</strong>。
                    </p>
                    <Button
                      onClick={handlePortalLogout}
                      variant="outline"
                      size="sm"
                      className="border-amber-400 text-amber-900 hover:bg-amber-100"
                    >
                      <LogOut className="h-4 w-4 mr-2" />
                      前往登出 NYCU Portal
                    </Button>
                  </div>
                </div>
              </div>
            )}

            <Button onClick={handleSSOLogin} className="w-full">
              <ExternalLink className="h-4 w-4 mr-2" />
              使用 NYCU Portal 登入
            </Button>
            <p className="text-center text-sm text-gray-600">
              請使用您的校園帳號登入 NYCU Portal 並授權登入系統
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
