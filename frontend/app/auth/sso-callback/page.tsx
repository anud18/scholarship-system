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

function SSOCallbackContent() {
  console.log("🚀 SSOCallbackContent component is rendering!");

  const router = useRouter();
  const searchParams = useSearchParams();
  const { login } = useAuth();
  const [status, setStatus] = useState<"loading" | "success" | "error">(
    "loading"
  );
  const [message, setMessage] = useState("");

  console.log("🔍 SearchParams available:", !!searchParams);
  console.log(
    "🔍 Current search params:",
    searchParams ? Object.fromEntries(searchParams.entries()) : "Not available"
  );

  useEffect(() => {
    const handleSSOCallback = async () => {
      try {
        // Get token and redirect path from URL parameters
        const token = searchParams.get("token");
        const redirectPath = searchParams.get("redirect") || "dashboard";

        console.log("🔐 SSO Callback - Starting authentication process");
        console.log(
          "📄 URL Search Params:",
          Object.fromEntries(searchParams.entries())
        );
        console.log(
          "🎟️ Token received:",
          !!token,
          token ? `${token.substring(0, 20)}...` : "none"
        );
        console.log("🔄 Redirect path:", redirectPath);

        if (!token) {
          console.error("❌ No token provided in URL parameters");
          throw new Error("No token provided");
        }

        // Decode JWT token directly to get user data
        console.log("🔓 Decoding JWT token directly...");
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
          console.log("🎫 Decoded token data:", tokenData);
          console.log("🔑 User role from token:", tokenData.role);
          console.log("🆔 User ID from token:", tokenData.nycu_id);

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

          console.log("👤 Constructed user data:", userData);

          // Use the login function from useAuth to set authentication state
          console.log("🔄 Calling login() with token and user data...");
          login(token, userData);
          console.log("✅ login() function called successfully");

          setStatus("success");
          setMessage("登入成功！正在重導向...");

          // Redirect based on user role
          const userRole = userData.role;
          let finalPath = "/";

          console.log("🎯 Determining redirect path based on role:", userRole);

          // Role-based redirection
          if (userRole === "admin" || userRole === "super_admin") {
            finalPath = "/#dashboard"; // Admin dashboard
            console.log("👑 Admin/Super Admin - redirecting to dashboard");
          } else if (userRole === "professor") {
            finalPath = "/#main"; // Professor review page
            console.log("🎓 Professor - redirecting to main");
          } else if (userRole === "college") {
            finalPath = "/#main"; // College dashboard
            console.log("🏫 College - redirecting to main");
          } else {
            finalPath = "/#main"; // Student portal
            console.log("🎒 Student - redirecting to main");
          }

          console.log("🚀 Final redirect path:", finalPath);

          setTimeout(() => {
            router.push(finalPath);
          }, 200);
        } catch (decodeError) {
          console.error("💥 Token decoding failed:", decodeError);
          console.error(
            "📡 Decode error details:",
            decodeError instanceof Error ? decodeError.message : decodeError
          );
          setStatus("error");
          setMessage("登入驗證失敗，請重新嘗試");

          console.log("🔄 Redirecting to login page after token decode error");
          // Redirect to login page after error
          setTimeout(() => {
            router.push("/");
          }, 3000);
        }
      } catch (error) {
        console.error("💥 SSO callback error:", error);
        console.error(
          "💥 Error details:",
          error instanceof Error ? error.message : error
        );
        console.error(
          "💥 Error stack:",
          error instanceof Error ? error.stack : "No stack trace"
        );
        setStatus("error");
        setMessage("登入失敗，請重新嘗試");

        console.log("🔄 Redirecting to login page after general error");
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
            <>
              <div className="h-8 w-8 mx-auto mb-4 text-green-600 flex items-center justify-center">
                <svg
                  className="h-8 w-8"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
              <p className="text-green-600 font-medium">{message}</p>
            </>
          )}

          {status === "error" && (
            <>
              <div className="h-8 w-8 mx-auto mb-4 text-red-600 flex items-center justify-center">
                <svg
                  className="h-8 w-8"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </div>
              <p className="text-red-600 font-medium">{message}</p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function SSOCallbackPage() {
  console.log("🎯 SSO Callback Page component is rendering!");
  console.log(
    "📍 Current location:",
    typeof window !== "undefined" ? window.location.href : "SSR"
  );

  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex items-center justify-center">
          <Card className="w-full max-w-md">
            <CardHeader className="text-center">
              <CardTitle className="text-2xl text-nycu-navy-800">
                Portal SSO 登入
              </CardTitle>
              <CardDescription>正在處理您的登入請求...</CardDescription>
            </CardHeader>
            <CardContent className="text-center">
              <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-nycu-blue-600" />
              <p className="text-nycu-navy-600">正在載入頁面...</p>
            </CardContent>
          </Card>
        </div>
      }
    >
      <SSOCallbackContent />
    </Suspense>
  );
}
