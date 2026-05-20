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

        // Decode JWT token directly to get user data
        try {
          // Simple JWT decode (we trust the token since it came from our backend)
          const base64Url = token.split(".")[1];
          const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
          const jsonPayload = decodeURIComponent(
            atob(base64)
              .split("")
              .map(function (c) {
                return "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2);
              })
              .join("")
          );

          const tokenData = JSON.parse(jsonPayload);
          logger.debug("JWT decoded", { role: tokenData.role });

          // Create user object from token data
          const userData = {
            id: tokenData.sub,
            nycu_id: tokenData.nycu_id,
            role: tokenData.role,
            name: tokenData.nycu_id, // Fallback, will be updated from backend later
            email: `${tokenData.nycu_id}@nycu.edu.tw`, // Placeholder
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          };

          // Use the login function from useAuth to set authentication state
          login(token, userData);
          logger.debug("login() called successfully");

          setStatus("success");
          setMessage("登入成功！正在重導向...");

          // Redirect based on user role
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
        } catch (decodeError) {
          logger.error("Token decoding failed", { decodeError });
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
