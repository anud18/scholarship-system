"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { SsoVerificationUnavailableError, verifySsoToken } from "@/lib/auth/verify-sso-token";
import { logger } from "@/lib/utils/logger";

function SSOCallbackContent() {
  logger.debug("SSOCallbackContent rendering");

  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();
  const [status, setStatus] = useState<"loading" | "success" | "error">(
    "loading"
  );
  const [message, setMessage] = useState("");

  logger.debug("SearchParams probe", {
    hasSearchParams: !!searchParams,
  });

  useEffect(() => {
    const handleSSOCallback = async () => {
      try {
        // Get token and redirect path from URL parameters
        const token = searchParams.get("token");
        const redirectPath = searchParams.get("redirect") || "dashboard";

        logger.debug("SSO Callback - starting authentication", {
          hasToken: !!token,
          redirectPath,
        });

        if (!token) {
          logger.error("No token provided in SSO callback URL parameters");
          throw new Error("No token provided");
        }

        // SECURITY (#1223 A): the token arrives in a URL, so it is attacker-
        // supplyable. Never decode its payload client-side and believe it — ask
        // the backend who it belongs to and use THAT answer.
        try {
          const userData = await verifySsoToken(token);
          logger.debug("SSO token verified by server", { role: userData.role });

          // Use the login function from useAuth to set authentication state
          login(token, userData);
          logger.debug("login() called successfully");

          setStatus("success");
          setMessage("登入成功！正在重導向...");

          // Redirect based on the SERVER-supplied role, not a URL-supplied claim.
          const userRole = userData.role;
          let finalPath = "/";

          // Role-based redirection
          if (userRole === "admin" || userRole === "super_admin") {
            finalPath = "/#dashboard"; // Admin dashboard
          } else if (userRole === "professor") {
            finalPath = "/#main"; // Professor review page
          } else if (userRole === "college") {
            finalPath = "/#main"; // College dashboard
          } else {
            finalPath = "/#main"; // Student portal
          }

          logger.debug("SSO redirect resolved", { role: userRole, finalPath });

          setTimeout(() => {
            router.push(finalPath);
          }, 200);
        } catch (verifyError) {
          // Distinguish "this token is bad" from "the server is having a moment".
          // Conflating them is what turned the 2025 attempt at this fix into a
          // login outage (see lib/auth/verify-sso-token.ts).
          if (verifyError instanceof SsoVerificationUnavailableError) {
            logger.error("SSO verification unavailable", { verifyError });
            setStatus("error");
            setMessage("無法連線至伺服器驗證登入，請稍後再試一次");
            // Deliberately NO auto-redirect: bouncing home would discard a
            // perfectly valid login over a transient blip.
            return;
          }

          logger.error("SSO token rejected", { verifyError });
          setStatus("error");
          setMessage("登入驗證失敗，請重新嘗試");

          // Redirect to login page after error
          setTimeout(() => {
            router.push("/");
          }, 3000);
        }
      } catch (error) {
        logger.error("SSO callback error", { error });
        setStatus("error");
        setMessage("登入失敗，請重新嘗試");

        // Redirect to login page after error
        setTimeout(() => {
          router.push("/");
        }, 3000);
      }
    };

    handleSSOCallback();
  }, [router, searchParams]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex items-center justify-center">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl text-nycu-navy-800">
            Portal SSO 登入
          </CardTitle>
          <CardDescription>正在處理您的登入請求...</CardDescription>
        </CardHeader>
        <CardContent className="text-center">
          {status === "loading" && (
            <>
              <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-nycu-blue-600" />
              <p className="text-nycu-navy-600">正在驗證登入資訊...</p>
            </>
          )}

          {status === "success" && (
            <div className="text-green-600">
              <p>{message}</p>
            </div>
          )}

          {status === "error" && (
            <div className="text-red-600">
              <p>{message}</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function SSOCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-nycu-blue-600" />
        </div>
      }
    >
      <SSOCallbackContent />
    </Suspense>
  );
}
