"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import apiClient from "@/lib/api";
import type { AuditLogEntry, AuditLogFilters } from "@/lib/api/modules/audit-logs";
import { logger } from "@/lib/utils/logger";
import { AlertCircle, ChevronDown, ChevronRight, RefreshCw, Search } from "lucide-react";
import { Fragment, useCallback, useEffect, useState } from "react";

const ACTION_OPTIONS = [
  "create",
  "update",
  "delete",
  "submit",
  "approve",
  "reject",
  "withdraw",
  "import",
  "execute_distribution",
  "revoke",
  "suspend",
  "restore",
];

const RESOURCE_OPTIONS = [
  "application",
  "scholarship_type",
  "scholarship_configuration",
  "college_ranking",
  "batch_import",
  "payment_roster",
];

const DESTRUCTIVE_ACTIONS = new Set(["delete", "revoke", "suspend", "reject"]);

export function AuditLogPanel() {
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filters, setFilters] = useState<AuditLogFilters>({});

  const fetchLogs = useCallback(
    async (targetPage: number) => {
      setLoading(true);
      setError(null);
      try {
        const response = await apiClient.auditLogs.list({
          ...filters,
          page: targetPage,
          size: 50,
        });
        if (response.success && response.data) {
          setItems(response.data.items);
          setTotal(response.data.total);
          setPages(response.data.pages);
          setPage(response.data.page);
        } else {
          setError(response.message || "載入稽核日誌失敗");
        }
      } catch (err: unknown) {
        logger.error("載入稽核日誌失敗", { error: err });
        setError("網路錯誤或伺服器未回應");
      } finally {
        setLoading(false);
      }
    },
    [filters],
  );

  useEffect(() => {
    fetchLogs(1);
  }, [fetchLogs]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>稽核日誌</CardTitle>
        <p className="text-sm text-muted-foreground">
          系統所有敏感操作的不可竄改紀錄（誰、何時、做了什麼、變更前後值）
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 篩選列 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Select
            value={filters.resource_type ?? "all"}
            onValueChange={(v) =>
              setFilters((f) => ({ ...f, resource_type: v === "all" ? undefined : v }))
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="資源類型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部資源</SelectItem>
              {RESOURCE_OPTIONS.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={filters.action ?? "all"}
            onValueChange={(v) => setFilters((f) => ({ ...f, action: v === "all" ? undefined : v }))}
          >
            <SelectTrigger>
              <SelectValue placeholder="操作" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部操作</SelectItem>
              {ACTION_OPTIONS.map((a) => (
                <SelectItem key={a} value={a}>
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            placeholder="資源 ID（如申請 DB id）"
            value={filters.resource_id ?? ""}
            onChange={(e) =>
              setFilters((f) => ({ ...f, resource_id: e.target.value || undefined }))
            }
          />
          <div className="flex gap-2">
            <Input
              placeholder="描述關鍵字"
              value={filters.search ?? ""}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value || undefined }))}
            />
            <Button onClick={() => fetchLogs(1)} disabled={loading} variant="outline" size="icon">
              {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2 text-red-700 text-sm">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        )}

        <div className="text-sm text-gray-600">共 {total} 筆紀錄</div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead>時間</TableHead>
              <TableHead>操作者</TableHead>
              <TableHead>操作</TableHead>
              <TableHead>資源</TableHead>
              <TableHead>描述</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((log) => (
              <Fragment key={log.id}>
                <TableRow
                  className="cursor-pointer"
                  onClick={() => setExpanded(expanded === log.id ? null : log.id)}
                >
                  <TableCell>
                    {expanded === log.id ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs whitespace-nowrap">
                    {log.created_at ? new Date(log.created_at).toLocaleString("zh-TW") : "—"}
                  </TableCell>
                  <TableCell>
                    {log.actor_name ?? "—"}
                    {log.actor_nycu_id && (
                      <span className="text-xs text-gray-500 ml-1">({log.actor_nycu_id})</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={DESTRUCTIVE_ACTIONS.has(log.action) ? "destructive" : "secondary"}>
                      {log.action}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {log.resource_type}
                    {log.resource_id ? `#${log.resource_id}` : ""}
                  </TableCell>
                  <TableCell className="text-sm max-w-md truncate">{log.description ?? "—"}</TableCell>
                </TableRow>
                {expanded === log.id && (
                  <TableRow>
                    <TableCell colSpan={6} className="bg-gray-50">
                      <div className="grid md:grid-cols-2 gap-3 text-xs p-2">
                        <div>
                          <div className="font-medium mb-1">變更前 (old_values)</div>
                          <pre className="bg-white border rounded p-2 overflow-auto max-h-48">
                            {JSON.stringify(log.old_values ?? null, null, 2)}
                          </pre>
                        </div>
                        <div>
                          <div className="font-medium mb-1">變更後 (new_values)</div>
                          <pre className="bg-white border rounded p-2 overflow-auto max-h-48">
                            {JSON.stringify(log.new_values ?? null, null, 2)}
                          </pre>
                        </div>
                        <div className="md:col-span-2 text-gray-600">
                          IP: {log.ip_address ?? "—"}　狀態: {log.status ?? "—"}
                          {log.meta_data && (
                            <>
                              　meta: <code>{JSON.stringify(log.meta_data)}</code>
                            </>
                          )}
                        </div>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
          </TableBody>
        </Table>

        {/* 分頁 */}
        <div className="flex justify-between items-center">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1 || loading}
            onClick={() => fetchLogs(page - 1)}
          >
            上一頁
          </Button>
          <span className="text-sm text-gray-600">
            第 {page} / {pages || 1} 頁
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages || loading}
            onClick={() => fetchLogs(page + 1)}
          >
            下一頁
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
