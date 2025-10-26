"use client";

import { useState, useEffect, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Clock, AlertCircle, Loader2, Activity } from "lucide-react";
import { apiClient } from "@/lib/api";
import { AuditLog } from "@/types/audit";
import { AuditLogItem } from "./audit-trail/AuditLogItem";
import { AuditLogFilters, FilterState } from "./audit-trail/AuditLogFilters";

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
  const [filters, setFilters] = useState<FilterState>({
    searchTerm: "",
    actionTypes: [],
    dateRange: { start: null, end: null },
  });

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

  const filteredLogs = useMemo(() => {
    return auditLogs.filter((log) => {
      // Search term filter
      if (filters.searchTerm) {
        const searchLower = filters.searchTerm.toLowerCase();
        const matchesSearch =
          log.description?.toLowerCase().includes(searchLower) ||
          log.user_name?.toLowerCase().includes(searchLower) ||
          log.ip_address?.toLowerCase().includes(searchLower) ||
          log.request_url?.toLowerCase().includes(searchLower);
        if (!matchesSearch) return false;
      }

      // Action type filter
      if (filters.actionTypes.length > 0) {
        if (!filters.actionTypes.includes(log.action)) return false;
      }

      // Date range filter
      if (filters.dateRange.start || filters.dateRange.end) {
        const logDate = new Date(log.created_at);
        if (
          filters.dateRange.start &&
          logDate < new Date(filters.dateRange.start)
        ) {
          return false;
        }
        if (
          filters.dateRange.end &&
          logDate > new Date(filters.dateRange.end)
        ) {
          return false;
        }
      }

      return true;
    });
  }, [auditLogs, filters]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="text-center space-y-3">
          <Loader2 className="h-10 w-10 animate-spin text-nycu-blue-600 mx-auto" />
          <p className="text-sm text-nycu-navy-600 font-medium">
            {locale === "zh" ? "載入操作紀錄中..." : "Loading audit trail..."}
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <Card className="border-red-200 bg-red-50">
        <CardContent className="pt-6">
          <div className="flex items-center justify-center">
            <AlertCircle className="h-8 w-8 text-red-600 mr-3" />
            <div>
              <h3 className="font-semibold text-red-900 mb-1">
                {locale === "zh" ? "載入失敗" : "Loading Failed"}
              </h3>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (auditLogs.length === 0) {
    return (
      <Card className="border-gray-200">
        <CardContent className="py-16">
          <div className="text-center space-y-4">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100">
              <Activity className="h-8 w-8 text-gray-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                {locale === "zh" ? "暫無操作紀錄" : "No Audit Trail"}
              </h3>
              <p className="text-sm text-gray-600 max-w-md mx-auto">
                {locale === "zh"
                  ? "此申請尚未有任何操作紀錄。當有人查看、修改或審核此申請時，相關記錄將會顯示在這裡。"
                  : "No operations have been performed on this application yet. Records will appear here when actions are taken."}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-gray-200 shadow-sm">
      <CardHeader className="border-b border-gray-100 bg-gradient-to-r from-gray-50 to-white">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2.5">
            <div className="p-2 bg-nycu-blue-100 rounded-lg">
              <Clock className="h-5 w-5 text-nycu-blue-600" />
            </div>
            <span className="text-xl">
              {locale === "zh" ? "操作紀錄" : "Audit Trail"}
            </span>
          </CardTitle>
          <Badge
            variant="secondary"
            className="ml-auto text-sm px-3 py-1 bg-gray-100 text-gray-700"
          >
            {auditLogs.length}{" "}
            {locale === "zh" ? "筆紀錄" : auditLogs.length === 1 ? "entry" : "entries"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="p-6">
        {/* Filters */}
        <AuditLogFilters
          filters={filters}
          onFiltersChange={setFilters}
          totalCount={auditLogs.length}
          filteredCount={filteredLogs.length}
          locale={locale}
        />

        {/* Timeline */}
        {filteredLogs.length === 0 ? (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-gray-100 mb-4">
              <AlertCircle className="h-7 w-7 text-gray-400" />
            </div>
            <h3 className="text-base font-semibold text-gray-700 mb-2">
              {locale === "zh" ? "無符合的紀錄" : "No matching records"}
            </h3>
            <p className="text-sm text-gray-500">
              {locale === "zh"
                ? "試試調整篩選條件或清除搜尋"
                : "Try adjusting your filters or clearing the search"}
            </p>
          </div>
        ) : (
          <ScrollArea className="h-[600px] pl-4">
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-4 top-2 bottom-0 w-px bg-gradient-to-b from-gray-300 via-gray-200 to-transparent" />

              {/* Timeline items */}
              <div className="space-y-0">
                {filteredLogs.map((log) => (
                  <AuditLogItem key={log.id} log={log} locale={locale} />
                ))}
              </div>
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
