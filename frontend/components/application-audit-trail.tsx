"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  FileText,
  Eye,
  Edit,
  Send,
  CheckCircle,
  XCircle,
  Upload,
  Trash2,
  Clock,
  User,
  Globe,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { apiClient } from "@/lib/api";
import { AuditLog } from "@/types/audit";

interface ApplicationAuditTrailProps {
  applicationId: number;
  locale?: "zh" | "en";
}

export function ApplicationAuditTrail({
  applicationId,
  locale = "zh",
}: ApplicationAuditTrailProps) {
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAuditTrail();
  }, [applicationId]);

  const fetchAuditTrail = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await apiClient.applications.getAuditTrail(applicationId);
      if (response.success) {
        setAuditLogs(response.data ?? []);
      } else {
        setError(response.message || "Failed to load audit trail");
      }
    } catch (err) {
      setError("Error loading audit trail");
      console.error("Failed to fetch audit trail:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const getActionIcon = (action: string) => {
    switch (action) {
      case "view":
        return <Eye className="h-4 w-4" />;
      case "update":
        return <Edit className="h-4 w-4" />;
      case "submit":
        return <Send className="h-4 w-4" />;
      case "approve":
        return <CheckCircle className="h-4 w-4" />;
      case "reject":
        return <XCircle className="h-4 w-4" />;
      case "create":
        return <Upload className="h-4 w-4" />;
      case "delete":
        return <Trash2 className="h-4 w-4" />;
      case "request_documents":
        return <FileText className="h-4 w-4" />;
      default:
        return <FileText className="h-4 w-4" />;
    }
  };

  const getActionColor = (action: string): string => {
    switch (action) {
      case "view":
        return "bg-blue-100 text-blue-700 border-blue-200";
      case "update":
        return "bg-yellow-100 text-yellow-700 border-yellow-200";
      case "submit":
        return "bg-purple-100 text-purple-700 border-purple-200";
      case "approve":
        return "bg-green-100 text-green-700 border-green-200";
      case "reject":
        return "bg-red-100 text-red-700 border-red-200";
      case "create":
        return "bg-indigo-100 text-indigo-700 border-indigo-200";
      case "delete":
        return "bg-gray-100 text-gray-700 border-gray-200";
      case "request_documents":
        return "bg-orange-100 text-orange-700 border-orange-200";
      default:
        return "bg-gray-100 text-gray-700 border-gray-200";
    }
  };

  const getActionLabel = (action: string): string => {
    const labels = {
      view: locale === "zh" ? "查看" : "View",
      update: locale === "zh" ? "更新" : "Update",
      submit: locale === "zh" ? "提交" : "Submit",
      approve: locale === "zh" ? "核准" : "Approve",
      reject: locale === "zh" ? "駁回" : "Reject",
      create: locale === "zh" ? "上傳" : "Upload",
      delete: locale === "zh" ? "刪除" : "Delete",
      request_documents: locale === "zh" ? "請求補件" : "Request Documents",
    };
    return labels[action as keyof typeof labels] || action;
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString(locale === "zh" ? "zh-TW" : "en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-8 w-8 animate-spin text-nycu-blue-600" />
        <span className="ml-2 text-nycu-navy-600">
          {locale === "zh" ? "載入操作紀錄中..." : "Loading audit trail..."}
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center p-8">
        <AlertCircle className="h-8 w-8 text-red-600 mr-2" />
        <span className="text-red-700">{error}</span>
      </div>
    );
  }

  if (auditLogs.length === 0) {
    return (
      <div className="text-center py-12">
        <Clock className="h-12 w-12 mx-auto mb-4 text-gray-300" />
        <h3 className="text-lg font-semibold text-gray-700 mb-2">
          {locale === "zh" ? "暫無操作紀錄" : "No Audit Trail"}
        </h3>
        <p className="text-gray-500">
          {locale === "zh"
            ? "此申請尚未有任何操作紀錄"
            : "No operations have been performed on this application yet"}
        </p>
      </div>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-5 w-5" />
          {locale === "zh" ? "操作紀錄" : "Audit Trail"}
          <Badge variant="secondary" className="ml-auto">
            {auditLogs.length} {locale === "zh" ? "筆紀錄" : "entries"}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[500px] pr-4">
          <div className="space-y-4">
            {auditLogs.map((log, index) => (
              <div
                key={log.id}
                className="relative pl-8 pb-6 border-l-2 border-gray-200 last:border-l-0 last:pb-0"
              >
                {/* Timeline dot */}
                <div
                  className={`absolute left-[-9px] top-0 h-4 w-4 rounded-full border-2 ${getActionColor(log.action)}`}
                >
                  <div className="absolute inset-0 flex items-center justify-center">
                    {getActionIcon(log.action)}
                  </div>
                </div>

                {/* Log content */}
                <div className="space-y-2">
                  {/* Header */}
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={getActionColor(log.action)}
                      >
                        {getActionLabel(log.action)}
                      </Badge>
                      <span className="text-sm font-medium text-gray-900">
                        {log.description}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500">
                      {formatDate(log.created_at)}
                    </span>
                  </div>

                  {/* User info */}
                  <div className="flex items-center gap-4 text-xs text-gray-600">
                    <div className="flex items-center gap-1">
                      <User className="h-3 w-3" />
                      <span>{log.user_name}</span>
                    </div>
                    {log.ip_address && (
                      <div className="flex items-center gap-1">
                        <Globe className="h-3 w-3" />
                        <span>{log.ip_address}</span>
                      </div>
                    )}
                    {log.request_method && log.request_url && (
                      <div className="flex items-center gap-1">
                        <code className="text-xs bg-gray-100 px-1 rounded">
                          {log.request_method} {log.request_url}
                        </code>
                      </div>
                    )}
                  </div>

                  {/* Changes (for update actions) */}
                  {(log.old_values || log.new_values) && (
                    <div className="mt-2 p-3 bg-gray-50 rounded-md text-xs">
                      {log.old_values && (
                        <div className="mb-2">
                          <span className="font-semibold text-gray-700">
                            {locale === "zh" ? "變更前：" : "Before: "}
                          </span>
                          <code className="text-gray-600">
                            {JSON.stringify(log.old_values)}
                          </code>
                        </div>
                      )}
                      {log.new_values && (
                        <div>
                          <span className="font-semibold text-gray-700">
                            {locale === "zh" ? "變更後：" : "After: "}
                          </span>
                          <code className="text-gray-600">
                            {JSON.stringify(log.new_values)}
                          </code>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Error message */}
                  {log.error_message && (
                    <div className="mt-2 p-3 bg-red-50 border border-red-200 rounded-md text-xs text-red-700">
                      <AlertCircle className="h-3 w-3 inline mr-1" />
                      {log.error_message}
                    </div>
                  )}

                  {/* Status indicator */}
                  {log.status && log.status !== "success" && (
                    <Badge
                      variant={
                        log.status === "failed" || log.status === "error"
                          ? "destructive"
                          : "secondary"
                      }
                      className="text-xs"
                    >
                      {log.status}
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
