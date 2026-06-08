"use client";

import { useState, useEffect } from "react";
import { logger } from "@/lib/utils/logger";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Loader2, Lock, LockOpen, X, AlertTriangle, RefreshCw, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import type { RevokedSuspendedList, DistributionDiff, DistributionDiffEntry } from "@/lib/api/modules/payment-rosters";
import { RevokedSuspendedSection } from "@/components/roster/RevokedSuspendedSection";

interface Period {
  label: string;
  status:
    | "completed"
    | "waiting"
    | "failed"
    | "processing"
    | "draft"
    | "locked";
  roster_id?: number;
  roster_code?: string;
  roster_status?: string;
  error_message?: string;
  completed_at?: string;
  total_amount?: number;
  qualified_count?: number;
  next_schedule?: string;
  period_start_date?: string;
  period_end_date?: string;
  sub_type?: string | null;
  allocation_year?: number | null;
  excel_stale?: boolean;
}

interface RosterDetailDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  period: Period;
  configId: number;
  /** Fired after any mutation that changes roster membership/state
   * (lock, unlock, reconcile, remove) so the parent can refetch its list
   * and the 人數 badge updates without a manual page reload. */
  onRosterChanged?: () => void;
}

interface RosterItem {
  id: number;
  student_name: string;
  student_id: string;
  student_id_number: string;
  student_email?: string;
  college_code?: string;
  college_name?: string;
  department_name?: string;
  scholarship_subtype: string;
  scholarship_amount: number;
  allocation_year?: number;
  bank_account?: string;
  is_included: boolean;
  exclusion_reason?: string | null;
  application_identity?: string;
  allocated_sub_type?: string;
}

type RosterAuditLogEntry = {
  id: number;
  action: string;
  title: string;
  description?: string | null;
  user_name?: string | null;
  created_at: string;
};

export function RosterDetailDialog({
  open,
  onOpenChange,
  period,
  configId,
  onRosterChanged,
}: RosterDetailDialogProps) {
  const [loading, setLoading] = useState(true);
  const [rosterItems, setRosterItems] = useState<RosterItem[]>([]);
  const [selectedCollege, setSelectedCollege] = useState<string>("");
  const [hasMatrix, setHasMatrix] = useState(false);

  // Revoked/suspended status change notice (Task 10)
  const [revokedSuspended, setRevokedSuspended] = useState<RevokedSuspendedList>({
    revoked: [],
    suspended: [],
  });
  const [removingItemId, setRemovingItemId] = useState<number | null>(null);

  const [isLocking, setIsLocking] = useState(false);
  const [isUnlocking, setIsUnlocking] = useState(false);

  // #66: exclude-item dialog state
  const [excludeTarget, setExcludeTarget] = useState<RosterItem | null>(null);
  const [excludeCategory, setExcludeCategory] = useState<
    "returned" | "declined" | "other"
  >("returned");
  const [excludeNote, setExcludeNote] = useState("");
  const [excludeSubmitting, setExcludeSubmitting] = useState(false);

  // 比對分發名單 (reconcile) state
  const [diff, setDiff] = useState<DistributionDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  // Per-row reconcile is single-action: a 待補充 row only adds, a 待移除 row only
  // removes. The pending row awaits confirmation before applying.
  const [pendingAction, setPendingAction] = useState<{
    kind: "add" | "remove";
    entry: DistributionDiffEntry;
  } | null>(null);
  const [reconcileSubmitting, setReconcileSubmitting] = useState(false);

  // Local mirror of excel_stale: the `period` prop is a snapshot from when the
  // dialog opened, so reconcile/remove mutations must flip the banner locally —
  // otherwise "需重新匯出 Excel" only shows after a full page reload.
  const [excelStale, setExcelStale] = useState(false);
  const [reExporting, setReExporting] = useState(false);
  const [showRemoved, setShowRemoved] = useState(true);
  const [restoringId, setRestoringId] = useState<number | null>(null);

  const [auditLogs, setAuditLogs] = useState<RosterAuditLogEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditFilter, setAuditFilter] = useState<
    "all" | "item_remove" | "item_add" | "item_restore"
  >("all");

  const canReconcile =
    period.roster_status === "completed" || period.roster_status === "locked";

  const openExcludeDialog = (item: RosterItem) => {
    setExcludeTarget(item);
    setExcludeCategory("returned");
    setExcludeNote("");
  };

  // Fetch revoked/suspended list when dialog opens for a locked roster
  useEffect(() => {
    if (!open || !period.roster_id || period.roster_status !== "locked") return;
    let cancelled = false;
    apiClient.paymentRosters.getRevokedSuspended(period.roster_id).then((resp) => {
      if (!cancelled && resp.success && resp.data) {
        setRevokedSuspended(resp.data);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [open, period.roster_id, period.roster_status]);

  const handleRemoveLockedItem = async (itemId: number, studentName: string) => {
    if (!period.roster_id) return;
    if (
      !confirm(
        `確認從本造冊移除 ${studentName}？(此操作會將造冊標記為「需重新匯出 Excel」)`
      )
    )
      return;
    setRemovingItemId(itemId);
    try {
      const resp = await apiClient.paymentRosters.removeItemFromLockedRoster(
        period.roster_id,
        itemId,
        undefined
      );
      if (resp.success) {
        const refresh = await apiClient.paymentRosters.getRevokedSuspended(
          period.roster_id
        );
        if (refresh.success && refresh.data) setRevokedSuspended(refresh.data);
        // Reload the dialog's own list so the removed row + 人數 drop instantly,
        // flip the stale banner locally, and notify the parent so its list
        // badge refreshes without a reload.
        await loadRosterItems();
        setExcelStale(true);
        onRosterChanged?.();
        toast.success(`已從造冊移除 ${studentName}`);
      } else {
        alert(resp.message || "移除失敗");
      }
    } finally {
      setRemovingItemId(null);
    }
  };

  const handleLockRoster = async () => {
    if (!period.roster_id) return;
    if (!confirm("確認鎖定此造冊？鎖定後將無法重新產生，但可解鎖。")) return;
    setIsLocking(true);
    try {
      const resp = await apiClient.paymentRosters.lockRoster(period.roster_id);
      if (resp.success) {
        toast.success("造冊已鎖定");
        onRosterChanged?.();
      } else {
        toast.error(resp.message || "鎖定失敗");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "鎖定失敗");
    } finally {
      setIsLocking(false);
    }
  };

  const handleUnlockRoster = async () => {
    if (!period.roster_id) return;
    if (!confirm("確認解鎖此造冊？解鎖後狀態將回到「已完成」。")) return;
    setIsUnlocking(true);
    try {
      const resp = await apiClient.paymentRosters.unlockRoster(period.roster_id);
      if (resp.success) {
        toast.success("造冊已解鎖");
        onRosterChanged?.();
      } else {
        toast.error(resp.message || "解鎖失敗");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "解鎖失敗");
    } finally {
      setIsUnlocking(false);
    }
  };

  const submitExclude = async () => {
    if (!excludeTarget || !period.roster_id) return;
    if (excludeCategory === "other" && !excludeNote.trim()) {
      toast.error("選擇「其他」時必須填寫補充說明");
      return;
    }
    setExcludeSubmitting(true);
    try {
      const response = await apiClient.paymentRosters.excludeRosterItem(
        period.roster_id,
        excludeTarget.id,
        excludeCategory,
        excludeNote.trim() || undefined
      );
      if (response.success) {
        toast.success(`已排除 ${excludeTarget.student_name} 的造冊明細`);
        setExcludeTarget(null);
        await loadRosterItems();
        await fetchAuditLogs();
      } else {
        toast.error(response.message || "排除失敗");
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : "排除失敗";
      toast.error(message);
    } finally {
      setExcludeSubmitting(false);
    }
  };

  const handleRestore = async (item: RosterItem) => {
    if (!period.roster_id) return;
    if (
      !window.confirm(
        `確定回復 ${item.student_name}？此操作會將造冊標記為「需重新匯出 Excel」`
      )
    ) {
      return;
    }
    setRestoringId(item.id);
    try {
      const resp = await apiClient.paymentRosters.restoreRosterItem(
        period.roster_id,
        item.id
      );
      if (resp.success) {
        toast.success(`已回復 ${item.student_name}`);
        setExcelStale(true);
        await loadRosterItems();
        await fetchAuditLogs();
      } else {
        toast.error(resp.message || "回復失敗");
      }
    } catch (e) {
      logger.error("restore roster item failed", { error: e });
      toast.error("回復失敗");
    } finally {
      setRestoringId(null);
    }
  };

  const loadDistributionDiff = async () => {
    if (!period.roster_id) return;
    setDiffLoading(true);
    try {
      const resp = await apiClient.paymentRosters.getDistributionDiff(period.roster_id);
      if (resp.success && resp.data) {
        setDiff(resp.data);
        setPendingAction(null);
      } else {
        // Drop any prior diff so a failed reload never leaves stale add/remove
        // candidates on screen for the admin to act on.
        setDiff(null);
        setPendingAction(null);
        toast.error(resp.message || "比對失敗");
      }
    } catch (e) {
      setDiff(null);
      setPendingAction(null);
      toast.error(e instanceof Error ? e.message : "比對失敗");
    } finally {
      setDiffLoading(false);
    }
  };

  // Apply a single-row add or remove. Each 待補充/待移除 row is one action — the
  // server still re-derives the allowed set and rejects anything stale.
  const applyReconcile = async (addIds: number[], removeItemIds: number[]) => {
    if (!period.roster_id) return;
    setReconcileSubmitting(true);
    try {
      const resp = await apiClient.paymentRosters.reconcileRoster(period.roster_id, {
        add_application_ids: addIds,
        remove_item_ids: removeItemIds,
      });
      if (resp.success) {
        const added = resp.data?.added.length ?? 0;
        const removed = resp.data?.removed.length ?? 0;
        toast.success(`已更新造冊名單：新增 ${added} 人 / 移除 ${removed} 人`);
        setPendingAction(null);
        // Independent refreshes — run in parallel to halve the post-apply wait.
        await Promise.all([loadRosterItems(), loadDistributionDiff()]);
        await fetchAuditLogs();
        if (resp.data?.excel_stale) setExcelStale(true);
        // Propagate to parent so its 人數 badge updates without a page reload.
        onRosterChanged?.();
      } else {
        toast.error(resp.message || "更新造冊名單失敗");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "更新造冊名單失敗");
    } finally {
      setReconcileSubmitting(false);
    }
  };

  const confirmPending = () => {
    if (!pendingAction) return;
    if (pendingAction.kind === "add") {
      applyReconcile([pendingAction.entry.application_id], []);
    } else if (pendingAction.entry.item_id != null) {
      applyReconcile([], [pendingAction.entry.item_id]);
    }
  };

  // Re-render the Excel from the current items; backend clears excel_stale on
  // success, so we drop the banner locally too.
  const handleReExport = async () => {
    if (!period.roster_id) return;
    setReExporting(true);
    try {
      const resp = await apiClient.paymentRosters.exportRoster(period.roster_id);
      if (resp.success) {
        setExcelStale(false);
        onRosterChanged?.();
        toast.success("Excel 已重新匯出");
      } else {
        toast.error(resp.message || "Excel 匯出失敗");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Excel 匯出失敗");
    } finally {
      setReExporting(false);
    }
  };

  useEffect(() => {
    if (open && period.roster_id) {
      loadRosterItems();
      fetchAuditLogs();
    }
  }, [open, period.roster_id]);

  // The dialog stays mounted while the parent swaps `period` between rosters,
  // so clear any prior roster's reconcile diff/selection when the roster (or
  // open state) changes — otherwise a stale diff could show under a new roster.
  useEffect(() => {
    setDiff(null);
    setPendingAction(null);
    setExcelStale(period.excel_stale ?? false);
  }, [open, period.roster_id, period.excel_stale]);

  const loadRosterItems = async () => {
    if (!period.roster_id) return;

    setLoading(true);
    try {
      const response = await apiClient.paymentRosters.getRosterItems(period.roster_id);

      if (response.success && response.data) {
        // バックエンドは { items: [...] } または [...] を返す可能性がある
        // Backend may return { items: [...] } or a bare array
        const raw = response.data as { items?: RosterItem[] } | RosterItem[];
        const items: RosterItem[] = Array.isArray(raw) ? raw : (raw.items ?? []);
        setRosterItems(items);

        // Check if has matrix (multiple colleges)
        const colleges = new Set(
          items.map((item: RosterItem) => item.college_code).filter(Boolean)
        );
        setHasMatrix(colleges.size > 1);

        if (colleges.size > 0) {
          const firstCollege = Array.from(colleges)[0];
          setSelectedCollege(firstCollege as string);
        }
      }
    } catch (error) {
      logger.error("Failed to load roster items", { error: error });
    } finally {
      setLoading(false);
    }
  };

  const fetchAuditLogs = async () => {
    if (!period.roster_id) return;
    setAuditLoading(true);
    try {
      const resp = await apiClient.paymentRosters.getAuditLogs(period.roster_id, {
        limit: 200,
      });
      const raw = (resp.data as { items?: RosterAuditLogEntry[] })?.items ?? [];
      setAuditLogs(raw);
    } catch (e) {
      logger.error("fetch roster audit logs failed", { error: e });
    } finally {
      setAuditLoading(false);
    }
  };

  const getItemsByCollege = (college: string): RosterItem[] => {
    return rosterItems.filter(item => item.college_code === college);
  };

  const colleges = Array.from(
    new Set(rosterItems.map(item => item.college_code).filter(Boolean))
  ).sort() as string[];

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("zh-TW", {
      style: "currency",
      currency: "TWD",
      minimumFractionDigits: 0,
    }).format(amount);
  };

  /** Find display name for a college code from the loaded items */
  const getCollegeDisplayName = (code: string): string => {
    const item = rosterItems.find(i => i.college_code === code);
    return item?.college_name || code;
  };

  const renderStudentTable = (items: RosterItem[]) => {
    const visibleItems = showRemoved ? items : items.filter(item => item.is_included);

    if (visibleItems.length === 0) {
      return (
        <div className="text-center py-8 text-muted-foreground">
          此學院無納入造冊的學生
        </div>
      );
    }

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>姓名</TableHead>
            <TableHead>學號</TableHead>
            <TableHead>系所</TableHead>
            <TableHead>申請身分</TableHead>
            <TableHead>分發獎學金</TableHead>
            <TableHead className="text-right">金額</TableHead>
            <TableHead className="text-right w-20">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visibleItems.map((item, index) => {
            const removed = !item.is_included;
            return (
              <TableRow
                key={index}
                className={removed ? "opacity-50 line-through" : undefined}
              >
                <TableCell className="font-medium">
                  {item.student_name}
                  {removed && (
                    <Badge variant="destructive" className="ml-2 no-underline">
                      已移除
                    </Badge>
                  )}
                  {removed && item.exclusion_reason && (
                    <span className="ml-2 text-xs text-muted-foreground no-underline">
                      {item.exclusion_reason}
                    </span>
                  )}
                </TableCell>
                <TableCell className="font-mono text-sm">
                  {item.student_id || "-"}
                </TableCell>
                <TableCell>{item.department_name || "-"}</TableCell>
                <TableCell>
                  <Badge
                    variant={
                      item.application_identity?.includes("續領")
                        ? "secondary"
                        : "outline"
                    }
                  >
                    {item.application_identity || "-"}
                  </Badge>
                </TableCell>
                <TableCell>
                  {item.allocated_sub_type ? (
                    <span className="text-sm">
                      {item.allocation_year && (
                        <span className="font-medium">
                          {item.allocation_year}年{" "}
                        </span>
                      )}
                      {item.allocated_sub_type === "nstc"
                        ? "國科會"
                        : item.allocated_sub_type === "moe_1w"
                          ? "教育部(1萬)"
                          : item.allocated_sub_type === "moe_2w"
                            ? "教育部(2萬)"
                            : item.allocated_sub_type}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">-</span>
                  )}
                </TableCell>
                <TableCell className="text-right font-medium">
                  {formatCurrency(item.scholarship_amount)}
                </TableCell>
                <TableCell className="text-right">
                  {removed ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={restoringId === item.id}
                      onClick={() => handleRestore(item)}
                      title="回復此明細（放回名單）"
                      className="no-underline"
                    >
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => openExcludeDialog(item)}
                      title="排除此明細（學生繳回 / 放棄）"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>造冊詳情 - {period.label}</DialogTitle>
          <DialogDescription>
            <span>造冊代碼: {period.roster_code}</span>
            {period.sub_type && (
              <span className="ml-3">
                獎學金類型:{" "}
                <Badge variant="outline" className="ml-1">
                  {period.sub_type}
                </Badge>
              </span>
            )}
            {period.allocation_year && (
              <span className="ml-3">
                配額年度:{" "}
                <Badge variant="secondary" className="ml-1">
                  {period.allocation_year}
                </Badge>
              </span>
            )}
          </DialogDescription>
        </DialogHeader>

        {/* Excel-stale banner — shows for any COMPLETED or LOCKED roster whose
            items changed (e.g. after a reconcile or a post-lock removal). */}
        {excelStale && (
          <div className="mb-3 p-3 border border-amber-300 bg-amber-50 rounded flex items-center justify-between">
            <span className="text-amber-800 text-sm">
              ⚠️ 造冊資料已變更，請重新匯出 Excel
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={handleReExport}
              disabled={reExporting}
            >
              {reExporting ? (
                <Loader2 className="h-4 w-4 animate-spin mr-1" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-1" />
              )}
              重新匯出 Excel
            </Button>
          </div>
        )}

        {/* Status-change notice panel (LOCKED rosters only — post-lock revoke/suspend) */}
        {period.roster_status === "locked" && (
          <>
            {(revokedSuspended.revoked.length > 0 ||
              revokedSuspended.suspended.length > 0) && (
              <div className="mb-4 space-y-3">
                <RevokedSuspendedSection
                  kind="revoked"
                  entries={revokedSuspended.revoked}
                  removingItemId={removingItemId}
                  onRemove={handleRemoveLockedItem}
                />
                <RevokedSuspendedSection
                  kind="suspended"
                  entries={revokedSuspended.suspended}
                  removingItemId={removingItemId}
                  onRemove={handleRemoveLockedItem}
                />
              </div>
            )}
          </>
        )}

        {canReconcile && (
          <div className="mb-4 p-3 border rounded">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">比對分發名單</span>
              <Button size="sm" variant="outline" onClick={loadDistributionDiff} disabled={diffLoading}>
                {diffLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                比對分發 vs 造冊
              </Button>
            </div>

            {diff && diff.to_add.length === 0 && diff.to_remove.length === 0 && (
              <p className="mt-2 text-sm text-muted-foreground">名單一致，無需補充。</p>
            )}

            {diff && diff.to_add.length > 0 && (
              <div className="mt-3">
                <p className="text-sm font-medium text-emerald-700">待補充 ({diff.to_add.length})</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>學號</TableHead>
                      <TableHead>姓名</TableHead>
                      <TableHead>系所</TableHead>
                      <TableHead className="text-right">金額</TableHead>
                      <TableHead className="w-20 text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {diff.to_add.map((e: DistributionDiffEntry) => (
                      <TableRow key={`add-${e.application_id}`}>
                        <TableCell>{e.student_id}</TableCell>
                        <TableCell>{e.student_name}</TableCell>
                        <TableCell>{e.department_name}</TableCell>
                        <TableCell className="text-right">{formatCurrency(e.scholarship_amount)}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-emerald-700 border-emerald-300 hover:bg-emerald-50"
                            disabled={reconcileSubmitting}
                            onClick={() => setPendingAction({ kind: "add", entry: e })}
                          >
                            新增
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {diff && diff.to_remove.length > 0 && (
              <div className="mt-3">
                <p className="text-sm font-medium text-red-700">待移除 ({diff.to_remove.length})</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>學號</TableHead>
                      <TableHead>姓名</TableHead>
                      <TableHead>系所</TableHead>
                      <TableHead className="w-20 text-right">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {diff.to_remove.map((e: DistributionDiffEntry) => (
                      <TableRow key={`rm-${e.item_id}`}>
                        <TableCell>{e.student_id}</TableCell>
                        <TableCell>{e.student_name}</TableCell>
                        <TableCell>{e.department_name}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-red-700 border-red-300 hover:bg-red-50"
                            disabled={reconcileSubmitting || e.item_id == null}
                            onClick={() => setPendingAction({ kind: "remove", entry: e })}
                          >
                            移除
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <span className="ml-2 text-muted-foreground">載入中...</span>
          </div>
        ) : hasMatrix ? (
          <Tabs value={selectedCollege} onValueChange={setSelectedCollege}>
            <TabsList
              className="grid w-full"
              style={{
                gridTemplateColumns: `repeat(${Math.min(colleges.length, 8)}, 1fr)`,
              }}
            >
              {colleges.map(college => {
                const count = getItemsByCollege(college).filter(
                  item => item.is_included
                ).length;
                return (
                  <TabsTrigger key={college} value={college}>
                    {getCollegeDisplayName(college)}
                    <Badge variant="secondary" className="ml-2">
                      {count}
                    </Badge>
                  </TabsTrigger>
                );
              })}
            </TabsList>

            {colleges.map(college => (
              <TabsContent key={college} value={college} className="mt-4">
                {renderStudentTable(getItemsByCollege(college))}
              </TabsContent>
            ))}
          </Tabs>
        ) : (
          <div className="mt-4">{renderStudentTable(rosterItems)}</div>
        )}

        {/* Summary */}
        <div className="mt-4 p-4 bg-muted rounded-lg">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">納入造冊人數:</span>
              <span className="ml-2 font-semibold">
                {rosterItems.filter(item => item.is_included).length} 人
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">總金額:</span>
              <span className="ml-2 font-semibold">
                {formatCurrency(
                  rosterItems
                    .filter(item => item.is_included)
                    .reduce(
                      (sum, item) => sum + Number(item.scholarship_amount),
                      0
                    )
                )}
              </span>
            </div>
          </div>
          <div className="mt-3">
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={showRemoved}
                onChange={e => setShowRemoved(e.target.checked)}
              />
              顯示已移除
            </label>
          </div>

          {period.roster_id && (
            <div className="mt-3 flex gap-2 justify-end">
              {period.roster_status !== "locked" ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleLockRoster}
                  disabled={isLocking}
                >
                  {isLocking ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  ) : (
                    <Lock className="h-4 w-4 mr-1" />
                  )}
                  鎖定造冊
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleUnlockRoster}
                  disabled={isUnlocking}
                >
                  {isUnlocking ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  ) : (
                    <LockOpen className="h-4 w-4 mr-1" />
                  )}
                  解鎖造冊
                </Button>
              )}
            </div>
          )}
        </div>

        {/* 操作紀錄 (audit trail) panel */}
        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-sm font-semibold">操作紀錄</h4>
            <div className="flex gap-2 text-sm">
              {(["all", "item_remove", "item_add", "item_restore"] as const).map(
                f => (
                  <button
                    key={f}
                    type="button"
                    className={
                      auditFilter === f
                        ? "font-semibold underline"
                        : "text-muted-foreground"
                    }
                    onClick={() => setAuditFilter(f)}
                  >
                    {
                      {
                        all: "全部",
                        item_remove: "移除",
                        item_add: "新增",
                        item_restore: "回復",
                      }[f]
                    }
                  </button>
                )
              )}
            </div>
          </div>
          {auditLoading ? (
            <div className="py-6 text-center text-muted-foreground">載入中…</div>
          ) : (
            <ul className="space-y-2 max-h-64 overflow-y-auto">
              {auditLogs
                .filter(l => auditFilter === "all" || l.action === auditFilter)
                .map(l => (
                  <li key={l.id} className="border rounded p-2 text-sm">
                    <div className="font-medium">{l.title}</div>
                    {l.description && (
                      <div className="text-muted-foreground">{l.description}</div>
                    )}
                    <div className="text-xs text-muted-foreground">
                      {l.user_name || "系統"} ·{" "}
                      {new Date(l.created_at).toLocaleString("zh-TW")}
                    </div>
                  </li>
                ))}
              {auditLogs.length === 0 && (
                <li className="py-6 text-center text-muted-foreground list-none">
                  尚無操作紀錄
                </li>
              )}
            </ul>
          )}
        </div>
      </DialogContent>

      {/* 比對分發名單 — single-row confirm */}
      <Dialog
        open={!!pendingAction}
        onOpenChange={open => !open && !reconcileSubmitting && setPendingAction(null)}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {pendingAction?.kind === "add" ? "確認補充進造冊" : "確認從造冊移除"}
            </DialogTitle>
            <DialogDescription className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 text-amber-500" />
              <span>
                {pendingAction?.kind === "add" ? "將補充 " : "將移除 "}
                <strong>{pendingAction?.entry.student_name}</strong>
                {pendingAction?.kind === "add" ? " 進造冊" : " 出造冊"}
                。此操作會將造冊標記為「需重新匯出 Excel」並記錄稽核日誌。
              </span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setPendingAction(null)}
              disabled={reconcileSubmitting}
            >
              取消
            </Button>
            <Button onClick={confirmPending} disabled={reconcileSubmitting}>
              {reconcileSubmitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              {pendingAction?.kind === "add" ? "確認新增" : "確認移除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* #66: exclude confirmation dialog */}
      <Dialog
        open={!!excludeTarget}
        onOpenChange={open => !open && !excludeSubmitting && setExcludeTarget(null)}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>排除造冊明細</DialogTitle>
            <DialogDescription>
              {excludeTarget && (
                <>
                  將從本期造冊中排除學生 <strong>{excludeTarget.student_name}</strong>
                  (學號 {excludeTarget.student_id})。
                  此動作會記錄稽核日誌且需指明原因。
                </>
              )}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="exclude-category">排除原因</Label>
              <Select
                value={excludeCategory}
                onValueChange={value =>
                  setExcludeCategory(value as "returned" | "declined" | "other")
                }
                disabled={excludeSubmitting}
              >
                <SelectTrigger id="exclude-category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="returned">學生繳回</SelectItem>
                  <SelectItem value="declined">學生放棄</SelectItem>
                  <SelectItem value="other">其他</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="exclude-note">
                補充說明
                {excludeCategory === "other" && (
                  <span className="text-red-500 ml-1">*</span>
                )}
              </Label>
              <Textarea
                id="exclude-note"
                value={excludeNote}
                onChange={e => setExcludeNote(e.target.value)}
                placeholder={
                  excludeCategory === "other"
                    ? "選擇「其他」時必填,請說明原因"
                    : "選填"
                }
                rows={3}
                disabled={excludeSubmitting}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setExcludeTarget(null)}
              disabled={excludeSubmitting}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={submitExclude}
              disabled={
                excludeSubmitting ||
                (excludeCategory === "other" && !excludeNote.trim())
              }
            >
              {excludeSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              確認排除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}
