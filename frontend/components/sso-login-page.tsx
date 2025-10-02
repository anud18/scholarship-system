"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { GraduationCap, ExternalLink } from "lucide-react";

export function SSOLoginPage() {
  const handleSSOLogin = () => {
    // Redirect to backend SSO endpoint
    window.location.href = `${process.env.NEXT_PUBLIC_NYCU_PORTAL_URL}/#/redirect/scholarship`;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="nycu-gradient h-16 w-16 rounded-xl flex items-center justify-center nycu-shadow mx-auto mb-4">
            <GraduationCap className="h-8 w-8 text-white" />
          </div>
          <CardTitle className="text-2xl text-nycu-navy-800">
            登入系統
          </CardTitle>
          <CardDescription>獎學金申請與簽核系統</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
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
