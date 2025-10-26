"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  FileText,
  Eye,
  Edit,
  Send,
  CheckCircle,
  XCircle,
  Upload,
  Trash2,
  User,
  Globe,
  AlertCircle,
  ChevronDown,
  Clock,
} from "lucide-react";
import { AuditLog } from "@/types/audit";
import { JsonDiffViewer } from "./JsonDiffViewer";

interface AuditLogItemProps {
  log: AuditLog;
  locale?: "zh" | "en";
}

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
      return "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100";
    case "update":
      return "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100";
    case "submit":
      return "bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100";
    case "approve":
      return "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100";
    case "reject":
      return "bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100";
    case "create":
      return "bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100";
    case "delete":
      return "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100";
    case "request_documents":
      return "bg-orange-50 text-orange-700 border-orange-200 hover:bg-orange-100";
    default:
      return "bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100";
  }
};

const getActionLabel = (action: string, locale: "zh" | "en"): string => {
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

const formatDate = (dateStr: string, locale: "zh" | "en") => {
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

const formatRelativeTime = (dateStr: string, locale: "zh" | "en") => {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return locale === "zh" ? "剛剛" : "Just now";
  if (diffMins < 60)
    return locale === "zh" ? `${diffMins} 分鐘前` : `${diffMins}m ago`;
  if (diffHours < 24)
    return locale === "zh" ? `${diffHours} 小時前` : `${diffHours}h ago`;
  if (diffDays < 7)
    return locale === "zh" ? `${diffDays} 天前` : `${diffDays}d ago`;

  return formatDate(dateStr, locale);
};

export function AuditLogItem({ log, locale = "zh" }: AuditLogItemProps) {
  const [isOpen, setIsOpen] = useState(false);

  const hasDetails =
    log.old_values ||
    log.new_values ||
    log.request_method ||
    log.request_url ||
    log.ip_address;

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setIsOpen}
      className="group relative"
    >
      <div className="relative pl-8">
        {/* Timeline dot with icon */}
        <div
          className={`absolute left-[2px] top-2 h-7 w-7 rounded-full border-2 ${getActionColor(
            log.action
          )} flex items-center justify-center shadow-sm transition-all duration-200 group-hover:scale-110`}
        >
          {getActionIcon(log.action)}
        </div>

        {/* Main card */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-all duration-200 overflow-hidden mb-6 mx-6">
          {/* Header - Always visible */}
          <div className="p-4">
            <div className="flex items-start justify-between gap-3 mb-3">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge
                  variant="outline"
                  className={`${getActionColor(log.action)} transition-colors`}
                >
                  {getActionLabel(log.action, locale)}
                </Badge>
                <span className="text-sm font-medium text-gray-900">
                  {log.description}
                </span>
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
              <div className="flex items-center gap-2 shrink-0">
                <div className="flex items-center gap-1 text-xs text-gray-500">
                  <Clock className="h-3 w-3" />
                  <span className="hidden sm:inline">
                    {formatRelativeTime(log.created_at, locale)}
                  </span>
                </div>
                {hasDetails && (
                  <CollapsibleTrigger asChild>
                    <button className="p-1.5 hover:bg-gray-100 rounded-md transition-colors">
                      <ChevronDown
                        className={`h-4 w-4 text-gray-500 transition-transform duration-200 ${
                          isOpen ? "rotate-180" : ""
                        }`}
                      />
                    </button>
                  </CollapsibleTrigger>
                )}
              </div>
            </div>

            {/* User info - Always visible */}
            <div className="flex items-center gap-3 text-xs text-gray-600">
              <div className="flex items-center gap-1.5">
                <User className="h-3.5 w-3.5" />
                <span className="font-medium">{log.user_name}</span>
              </div>
              <span className="hidden sm:inline text-gray-400">•</span>
              <span className="hidden sm:inline">
                {formatDate(log.created_at, locale)}
              </span>
            </div>
          </div>

          {/* Expandable details */}
          {hasDetails && (
            <CollapsibleContent>
              <div className="border-t border-gray-100 bg-gray-50/50 p-4 space-y-4">
                {/* IP and Request info */}
                {(log.ip_address || log.request_method || log.request_url) && (
                  <div className="space-y-2">
                    {log.ip_address && (
                      <div className="flex items-center gap-2 text-xs text-gray-600">
                        <Globe className="h-3.5 w-3.5" />
                        <span className="font-mono">{log.ip_address}</span>
                      </div>
                    )}
                    {log.request_method && log.request_url && (
                      <div className="flex items-center gap-2 text-xs">
                        <code className="bg-gray-100 px-2 py-1 rounded font-mono text-gray-700 border border-gray-200">
                          {log.request_method}
                        </code>
                        <code className="bg-gray-100 px-2 py-1 rounded font-mono text-gray-700 border border-gray-200 flex-1 truncate">
                          {log.request_url}
                        </code>
                      </div>
                    )}
                  </div>
                )}

                {/* Changes diff viewer */}
                {(log.old_values || log.new_values) && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
                      {locale === "zh" ? "變更內容" : "Changes"}
                    </h4>
                    <JsonDiffViewer
                      oldValue={log.old_values}
                      newValue={log.new_values}
                      locale={locale}
                    />
                  </div>
                )}

                {/* Error message */}
                {log.error_message && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                      <div>
                        <h4 className="text-xs font-semibold text-red-900 mb-1">
                          {locale === "zh" ? "錯誤訊息" : "Error Message"}
                        </h4>
                        <p className="text-xs text-red-700">
                          {log.error_message}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </CollapsibleContent>
          )}
        </div>
      </div>
    </Collapsible>
  );
}
