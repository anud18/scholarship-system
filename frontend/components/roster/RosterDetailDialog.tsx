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
import { Loader2, Lock, LockOpen, X } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import type { RevokedSuspendedList } from "@/lib/api/modules/payment-rosters";

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
  onLockStateChange?: () => void;
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

export function RosterDetailDialog({
  open,
  onOpenChange,
  period,
  configId,
  onLockStateChange,
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
        // No onChanged callback on this dialog; parent will see updated state
        // the next time it opens. To propagate excel_stale, a full reload of
        // roster list data would be needed — wire onChanged if added to props later.
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
        onLockStateChange?.();
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
        onLockStateChange?.();
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

  useEffect(() => {
    if (open && period.roster_id) {
      loadRosterItems();
    }
  }, [open, period.roster_id]);

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
    const includedItems = items.filter(item => item.is_included);

    if (includedItems.length === 0) {
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
          {includedItems.map((item, index) => (
            <TableRow key={index}>
              <TableCell className="font-medium">{item.student_name}</TableCell>
              <TableCell className="font-mono text-sm">
                {item.student_id_number}
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
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => openExcludeDialog(item)}
                  title="排除此明細(學生繳回 / 放棄)"
                >
                  <X className="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          ))}
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

        {/* Task 10: Status-change notice panel + Excel-stale banner (LOCKED rosters only) */}
        {period.roster_status === "locked" && (
          <>
            {period.excel_stale && (
              <div className="mb-3 p-3 border border-amber-300 bg-amber-50 rounded flex items-center justify-between">
                <span className="text-amber-800 text-sm">
                  ⚠️ 造冊資料已變更，請重新匯出 Excel
                </span>
                {/* Reuse existing "重新匯出 Excel" handler if wired in this component in future */}
              </div>
            )}

            {(revokedSuspended.revoked.length > 0 ||
              revokedSuspended.suspended.length > 0) && (
              <div className="mb-4 space-y-3">
                {revokedSuspended.revoked.length > 0 && (
                  <details
                    open
                    className="border border-red-300 bg-red-50 rounded p-3"
                  >
                    <summary className="text-red-800 font-semibold cursor-pointer text-sm">
                      ⚠️ 此造冊有 {revokedSuspended.revoked.length}{" "}
                      位學生被撤銷，請手動處理
                    </summary>
                    <ul className="mt-2 space-y-2">
                      {revokedSuspended.revoked.map((s) => (
                        <li
                          key={s.application_id}
                          className="text-sm flex items-start justify-between gap-3"
                        >
                          <div>
                            <div>
                              <span className="font-medium">{s.student_name}</span>
                              <span className="text-slate-500">
                                {" "}
                                ({s.student_id_number})
                              </span>
                              <span className="text-xs text-slate-500 ml-2">
                                撤銷於 {new Date(s.event_at).toLocaleDateString()}
                              </span>
                            </div>
                            {s.reason && (
                              <div className="text-xs text-slate-600">
                                原因：{s.reason}
                              </div>
                            )}
                          </div>
                          {s.item_id !== null && (
                            <button
                              onClick={() =>
                                handleRemoveLockedItem(s.item_id!, s.student_name)
                              }
                              disabled={removingItemId === s.item_id}
                              className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 whitespace-nowrap"
                            >
                              {removingItemId === s.item_id
                                ? "處理中…"
                                : "從本造冊移除"}
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}

                {revokedSuspended.suspended.length > 0 && (
                  <details
                    open
                    className="border border-slate-300 bg-slate-50 rounded p-3"
                  >
                    <summary className="text-slate-700 font-semibold cursor-pointer text-sm">
                      ℹ️ 此造冊有 {revokedSuspended.suspended.length}{" "}
                      位學生被停發（僅資訊）
                    </summary>
                    <ul className="mt-2 space-y-1">
                      {revokedSuspended.suspended.map((s) => (
                        <li key={s.application_id} className="text-sm">
                          <span className="font-medium">{s.student_name}</span>
                          <span className="text-slate-500">
                            {" "}
                            ({s.student_id_number})
                          </span>
                          <span className="text-xs text-slate-500 ml-2">
                            停發於 {new Date(s.event_at).toLocaleDateString()}
                          </span>
                          {s.reason && (
                            <div className="text-xs text-slate-600">
                              原因：{s.reason}
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </>
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
      </DialogContent>

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
