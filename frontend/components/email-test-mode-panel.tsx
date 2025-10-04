"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle, Clock, Mail, RefreshCw, Shield } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { TagsInput } from "@/components/ui/tags-input";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";

interface TestModeStatus {
  enabled: boolean;
  redirect_emails: string[];
  expires_at: string | null;
  enabled_by?: number;
  enabled_at?: string;
}

interface AuditLog {
  id: number;
  event_type: string;
  timestamp: string;
  user_id: number | null;
  config_before: any;
  config_after: any;
  original_recipient: string | null;
  actual_recipient: string | null;
  email_subject: string | null;
  session_id: string | null;
  ip_address: string | null;
}

export function EmailTestModePanel() {
  const { toast } = useToast();
  const [status, setStatus] = useState<TestModeStatus>({
    enabled: false,
    redirect_emails: [],
    expires_at: null,
  });
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [showEnableDialog, setShowEnableDialog] = useState(false);
  const [showDisableDialog, setShowDisableDialog] = useState(false);
  const [redirectEmails, setRedirectEmails] = useState<string[]>([]);
  const [durationHours, setDurationHours] = useState(24);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [showAuditLogs, setShowAuditLogs] = useState(false);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      setRefreshing(true);
      const response = await api.emailManagement.getTestModeStatus();
      if (response.success && response.data) {
        setStatus(response.data);
      }
    } catch (error) {
      console.error("Failed to load test mode status:", error);
      toast({
        variant: "destructive",
        title: "載入失敗",
        description: "無法載入測試模式狀態",
      });
    } finally {
      setRefreshing(false);
    }
  };

  const loadAuditLogs = async () => {
    try {
      const response = await api.emailManagement.getTestModeAuditLogs({ limit: 50 });
      if (response.success && response.data) {
        setAuditLogs(response.data.items);
      }
    } catch (error) {
      console.error("Failed to load audit logs:", error);
    }
  };

  const handleEnable = async () => {
    // Validate at least one email
    if (redirectEmails.length === 0) {
      toast({
        variant: "destructive",
        title: "驗證失敗",
        description: "請輸入至少一個測試信箱地址",
      });
      return;
    }

    try {
      setLoading(true);
      const response = await api.emailManagement.enableTestMode({
        redirect_emails: redirectEmails,
        duration_hours: durationHours,
      });

      if (response.success) {
        setStatus(response.data!);
        setShowEnableDialog(false);
        setRedirectEmails([]);
        toast({
          title: "測試模式已啟用",
          description: `所有郵件將重定向到 ${redirectEmails.length} 個測試信箱，將於 ${durationHours} 小時後自動關閉`,
        });
      }
    } catch (error: any) {
      toast({
        variant: "destructive",
        title: "啟用失敗",
        description: error.message || "無法啟用測試模式",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleDisable = async () => {
    try {
      setLoading(true);
      const response = await api.emailManagement.disableTestMode();

      if (response.success) {
        setStatus(response.data!);
        setShowDisableDialog(false);
        toast({
          title: "測試模式已停用",
          description: "郵件將正常發送至實際收件人",
        });
      }
    } catch (error: any) {
      toast({
        variant: "destructive",
        title: "停用失敗",
        description: error.message || "無法停用測試模式",
      });
    } finally {
      setLoading(false);
    }
  };

  const formatExpiryTime = (expiresAt: string | null) => {
    if (!expiresAt) return null;
    const expiry = new Date(expiresAt);
    const now = new Date();
    const diffMs = expiry.getTime() - now.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

    if (diffMs < 0) return "已過期";
    if (diffHours > 0) return `${diffHours} 小時 ${diffMinutes} 分鐘`;
    return `${diffMinutes} 分鐘`;
  };

  const getEventTypeLabel = (eventType: string) => {
    const labels: Record<string, string> = {
      enabled: "啟用",
      disabled: "停用",
      expired: "過期",
      email_intercepted: "郵件攔截",
      config_updated: "配置更新",
    };
    return labels[eventType] || eventType;
  };

  return (
    <div className="space-y-6">
      {/* Status Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              郵件測試模式
            </CardTitle>
            <CardDescription>
              重定向所有外發郵件至測試信箱，用於生產環境安全測試
            </CardDescription>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={loadStatus}
            disabled={refreshing}
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Current Status */}
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div className="flex items-center gap-3 flex-1">
              <div
                className={`h-3 w-3 rounded-full flex-shrink-0 ${
                  status.enabled ? "bg-yellow-500 animate-pulse" : "bg-gray-300"
                }`}
              />
              <div className="flex-1 min-w-0">
                <p className="font-medium">
                  {status.enabled ? "測試模式啟用中" : "測試模式已停用"}
                </p>
                {status.enabled && status.redirect_emails && status.redirect_emails.length > 0 && (
                  <div className="mt-2">
                    <p className="text-sm text-muted-foreground mb-1">
                      郵件重定向至 {status.redirect_emails.length} 個測試信箱:
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {status.redirect_emails.map((email, idx) => (
                        <Badge key={idx} variant="outline" className="text-xs">
                          {email}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
            <Badge variant={status.enabled ? "warning" : "secondary"} className="flex-shrink-0">
              {status.enabled ? "啟用" : "停用"}
            </Badge>
          </div>

          {/* Expiry Information */}
          {status.enabled && status.expires_at && (
            <Alert>
              <Clock className="h-4 w-4" />
              <AlertTitle>自動過期時間</AlertTitle>
              <AlertDescription>
                剩餘時間: {formatExpiryTime(status.expires_at)}
                <br />
                <span className="text-xs text-muted-foreground">
                  {new Date(status.expires_at).toLocaleString("zh-TW")}
                </span>
              </AlertDescription>
            </Alert>
          )}

          {/* Warning when enabled */}
          {status.enabled && (
            <Alert variant="warning">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>注意</AlertTitle>
              <AlertDescription>
                測試模式啟用期間，所有系統郵件將不會發送給實際收件人。
                <br />
                請確保您了解這個設定的影響，並在測試完成後立即停用。
              </AlertDescription>
            </Alert>
          )}

          {/* Action Buttons */}
          <div className="flex gap-3">
            {!status.enabled ? (
              <Button
                onClick={() => setShowEnableDialog(true)}
                className="flex-1"
                variant="default"
              >
                <Mail className="h-4 w-4 mr-2" />
                啟用測試模式
              </Button>
            ) : (
              <Button
                onClick={() => setShowDisableDialog(true)}
                className="flex-1"
                variant="destructive"
              >
                <AlertCircle className="h-4 w-4 mr-2" />
                停用測試模式
              </Button>
            )}
            <Button
              onClick={() => {
                setShowAuditLogs(true);
                loadAuditLogs();
              }}
              variant="outline"
            >
              檢視稽核記錄
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Enable Dialog */}
      <Dialog open={showEnableDialog} onOpenChange={setShowEnableDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>啟用郵件測試模式</DialogTitle>
            <DialogDescription>
              所有外發郵件將重定向至指定的測試信箱
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="redirect-email">測試信箱地址</Label>
              <TagsInput
                value={redirectEmails}
                onChange={setRedirectEmails}
                placeholder="輸入測試信箱後按 Enter 或逗號新增"
                validator={(email) => email.includes("@")}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                輸入測試信箱後按 Enter 或逗號新增 • 點擊 ✕ 移除標籤 • 支援貼上多個信箱（自動分隔）
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="duration">持續時間（小時）</Label>
              <Select
                value={durationHours.toString()}
                onValueChange={(value) => setDurationHours(Number(value))}
              >
                <SelectTrigger id="duration">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1 小時</SelectItem>
                  <SelectItem value="4">4 小時</SelectItem>
                  <SelectItem value="8">8 小時</SelectItem>
                  <SelectItem value="24">24 小時（預設）</SelectItem>
                  <SelectItem value="48">48 小時</SelectItem>
                  <SelectItem value="72">72 小時</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                測試模式將在指定時間後自動停用
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowEnableDialog(false)}
              disabled={loading}
            >
              取消
            </Button>
            <Button onClick={handleEnable} disabled={loading}>
              {loading ? "啟用中..." : "確認啟用"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Disable Dialog */}
      <Dialog open={showDisableDialog} onOpenChange={setShowDisableDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>停用郵件測試模式</DialogTitle>
            <DialogDescription>
              確定要停用測試模式嗎？郵件將恢復正常發送。
            </DialogDescription>
          </DialogHeader>
          <Alert>
            <CheckCircle className="h-4 w-4" />
            <AlertTitle>提醒</AlertTitle>
            <AlertDescription>
              停用後，系統郵件將立即恢復發送給實際收件人。
            </AlertDescription>
          </Alert>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDisableDialog(false)}
              disabled={loading}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDisable}
              disabled={loading}
            >
              {loading ? "停用中..." : "確認停用"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Audit Logs Dialog */}
      <Dialog open={showAuditLogs} onOpenChange={setShowAuditLogs}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>測試模式稽核記錄</DialogTitle>
            <DialogDescription>
              檢視測試模式的啟用、停用及郵件攔截記錄
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {auditLogs.length === 0 ? (
              <p className="text-center text-muted-foreground py-8">暫無稽核記錄</p>
            ) : (
              auditLogs.map((log) => (
                <div key={log.id} className="border rounded-lg p-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <Badge variant={log.event_type === "enabled" ? "warning" : "secondary"}>
                      {getEventTypeLabel(log.event_type)}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {new Date(log.timestamp).toLocaleString("zh-TW")}
                    </span>
                  </div>
                  {log.event_type === "email_intercepted" && (
                    <div className="text-sm">
                      <p>
                        <span className="font-medium">原收件人:</span> {log.original_recipient}
                      </p>
                      <p>
                        <span className="font-medium">實際發送:</span> {log.actual_recipient}
                      </p>
                      <p className="text-muted-foreground truncate">
                        <span className="font-medium">主旨:</span> {log.email_subject}
                      </p>
                    </div>
                  )}
                  {log.ip_address && (
                    <p className="text-xs text-muted-foreground">IP: {log.ip_address}</p>
                  )}
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
