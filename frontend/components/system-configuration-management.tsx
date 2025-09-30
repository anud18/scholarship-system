"use client";

import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Edit2,
  Save,
  X,
  History,
  AlertTriangle,
  Settings,
  Shield,
  Mail,
  Key,
  FileText,
  Camera,
  Lock,
  Unlock,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import {
  apiClient,
  SystemConfiguration,
  SystemConfigurationUpdate,
} from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";

// Category configuration
const categoryConfig = {
  email: {
    label: "電子郵件設定",
    icon: Mail,
    description: "SMTP 伺服器和寄件者設定",
  },
  ocr: {
    label: "OCR 設定",
    icon: Camera,
    description: "文件辨識服務配置",
  },
  file_storage: {
    label: "檔案儲存設定",
    icon: FileText,
    description: "檔案上傳限制和規則",
  },
  security: {
    label: "安全設定",
    icon: Shield,
    description: "權杖過期時間和安全策略",
  },
  api_keys: {
    label: "API 金鑰",
    icon: Key,
    description: "第三方服務 API 金鑰",
  },
  performance: {
    label: "效能設定",
    icon: Settings,
    description: "快取和效能優化配置",
  },
};

type CategoryKey = keyof typeof categoryConfig;

export default function SystemConfigurationManagement() {
  const { user } = useAuth();
  const [configurations, setConfigurations] = useState<SystemConfiguration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSensitive, setShowSensitive] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editFormData, setEditFormData] = useState<Record<string, any>>({});
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());
  const [selectedConfigKey, setSelectedConfigKey] = useState<string>("");
  const [auditLogs, setAuditLogs] = useState<any[]>([]);

  useEffect(() => {
    loadConfigurations();
  }, [showSensitive]);

  const loadConfigurations = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.system.getConfigurations(undefined, showSensitive);
      if (response.success && response.data) {
        setConfigurations(response.data);
      } else {
        setError(response.message || "無法載入配置");
      }
    } catch (err) {
      setError("載入配置時發生錯誤");
      console.error("Error loading configurations:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadAuditLogs = async (configKey: string) => {
    try {
      const response = await apiClient.system.getAuditLogs(configKey, 20);
      if (response.success && response.data) {
        setAuditLogs(response.data);
      }
    } catch (err) {
      console.error("Error loading audit logs:", err);
    }
  };

  const handleEdit = (config: SystemConfiguration) => {
    setEditingKey(config.key);
    setEditFormData({
      value: config.value,
      description: config.description || "",
    });
  };

  const handleCancelEdit = () => {
    setEditingKey(null);
    setEditFormData({});
  };

  const handleSave = async (config: SystemConfiguration) => {
    try {
      const updateData: SystemConfigurationUpdate = {
        value: editFormData.value,
        category: config.category,
        data_type: config.data_type,
        is_sensitive: config.is_sensitive,
        description: editFormData.description,
      };

      const response = await apiClient.system.updateConfiguration(config.key, updateData);
      if (response.success) {
        setEditingKey(null);
        setEditFormData({});
        loadConfigurations();
      } else {
        setError(response.message || "更新配置失敗");
      }
    } catch (err) {
      setError("更新配置時發生錯誤");
      console.error("Error updating configuration:", err);
    }
  };

  const toggleCategory = (category: string) => {
    const newCollapsed = new Set(collapsedCategories);
    if (newCollapsed.has(category)) {
      newCollapsed.delete(category);
    } else {
      newCollapsed.add(category);
    }
    setCollapsedCategories(newCollapsed);
  };

  const openAuditDialog = (configKey: string) => {
    setSelectedConfigKey(configKey);
    loadAuditLogs(configKey);
  };

  // Group configurations by category
  const groupedConfigs = configurations.reduce((acc, config) => {
    if (!acc[config.category]) {
      acc[config.category] = [];
    }
    acc[config.category].push(config);
    return acc;
  }, {} as Record<string, SystemConfiguration[]>);

  // Render input based on data type
  const renderValueInput = (config: SystemConfiguration) => {
    const value = editFormData.value;

    if (config.data_type === "boolean") {
      return (
        <div className="flex items-center space-x-2">
          <Switch
            checked={value === "true" || value === true}
            onCheckedChange={(checked) =>
              setEditFormData({ ...editFormData, value: checked ? "true" : "false" })
            }
          />
          <span className="text-sm text-muted-foreground">
            {value === "true" || value === true ? "已啟用" : "已停用"}
          </span>
        </div>
      );
    }

    if (config.data_type === "integer") {
      return (
        <Input
          type="number"
          value={value}
          onChange={(e) => setEditFormData({ ...editFormData, value: e.target.value })}
          className="max-w-xs"
        />
      );
    }

    // String or other types
    if (value && value.length > 50) {
      return (
        <Textarea
          value={value}
          onChange={(e) => setEditFormData({ ...editFormData, value: e.target.value })}
          rows={3}
          className="font-mono text-sm"
        />
      );
    }

    return (
      <Input
        type={config.is_sensitive ? "password" : "text"}
        value={value}
        onChange={(e) => setEditFormData({ ...editFormData, value: e.target.value })}
        className="font-mono text-sm"
      />
    );
  };

  // Render display value
  const renderDisplayValue = (config: SystemConfiguration) => {
    if (config.is_sensitive && !showSensitive) {
      return <span className="text-muted-foreground">***HIDDEN***</span>;
    }

    if (config.data_type === "boolean") {
      const isEnabled = config.value === "true" || config.value === true;
      return (
        <div className="flex items-center space-x-2">
          <div
            className={`w-2 h-2 rounded-full ${isEnabled ? "bg-green-500" : "bg-gray-400"}`}
          />
          <span>{isEnabled ? "已啟用" : "已停用"}</span>
        </div>
      );
    }

    return (
      <span className="font-mono text-sm">
        {config.value.length > 100
          ? config.value.substring(0, 100) + "..."
          : config.value}
      </span>
    );
  };

  if (!user || (user.role !== "admin" && user.role !== "super_admin")) {
    return (
      <div className="p-6">
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>您沒有權限存取系統配置管理功能。</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold">系統配置管理</h1>
          <p className="text-muted-foreground mt-1">
            即時生效配置 • 修改後立即套用，無需重啟服務
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            {showSensitive ? (
              <Unlock className="h-4 w-4 text-orange-500" />
            ) : (
              <Lock className="h-4 w-4 text-gray-500" />
            )}
            <Label htmlFor="show-sensitive" className="cursor-pointer">
              顯示敏感資料
            </Label>
            <Switch
              id="show-sensitive"
              checked={showSensitive}
              onCheckedChange={setShowSensitive}
            />
          </div>
          <Button onClick={loadConfigurations} variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            重新載入
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading ? (
        <div className="text-center py-12">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-muted-foreground" />
          <p className="text-muted-foreground mt-4">載入配置中...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {Object.entries(categoryConfig).map(([categoryKey, category]) => {
            const configs = groupedConfigs[categoryKey] || [];
            if (configs.length === 0) return null;

            const CategoryIcon = category.icon;
            const isCollapsed = collapsedCategories.has(categoryKey);

            return (
              <Card key={categoryKey} className="overflow-hidden">
                <CardHeader
                  className="cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() => toggleCategory(categoryKey)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <CategoryIcon className="h-5 w-5 text-primary" />
                      <div>
                        <CardTitle className="text-lg">{category.label}</CardTitle>
                        <CardDescription className="text-xs mt-1">
                          {category.description} • {configs.length} 項配置
                        </CardDescription>
                      </div>
                    </div>
                    {isCollapsed ? (
                      <ChevronDown className="h-5 w-5 text-muted-foreground" />
                    ) : (
                      <ChevronUp className="h-5 w-5 text-muted-foreground" />
                    )}
                  </div>
                </CardHeader>

                {!isCollapsed && (
                  <CardContent className="space-y-4 pt-0">
                    {configs.map((config) => (
                      <div
                        key={config.key}
                        className="p-4 rounded-lg border bg-card hover:bg-muted/30 transition-colors"
                      >
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1">
                            <div className="flex items-center space-x-2 mb-1">
                              <span className="font-mono text-sm font-medium">
                                {config.key}
                              </span>
                              {config.is_sensitive && (
                                <Badge variant="secondary" className="text-xs">
                                  <Lock className="h-3 w-3 mr-1" />
                                  敏感
                                </Badge>
                              )}
                              <Badge variant="outline" className="text-xs">
                                {config.data_type}
                              </Badge>
                            </div>
                            {config.description && (
                              <p className="text-sm text-muted-foreground">
                                {config.description}
                              </p>
                            )}
                          </div>
                          <div className="flex items-center space-x-1 ml-4">
                            {editingKey !== config.key && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleEdit(config)}
                                  className="h-8"
                                >
                                  <Edit2 className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openAuditDialog(config.key)}
                                  className="h-8"
                                >
                                  <History className="h-4 w-4" />
                                </Button>
                              </>
                            )}
                          </div>
                        </div>

                        {editingKey === config.key ? (
                          <div className="space-y-3 mt-4 pt-4 border-t">
                            <div className="space-y-2">
                              <Label>配置值</Label>
                              {renderValueInput(config)}
                            </div>
                            <div className="space-y-2">
                              <Label>描述</Label>
                              <Input
                                value={editFormData.description}
                                onChange={(e) =>
                                  setEditFormData({
                                    ...editFormData,
                                    description: e.target.value,
                                  })
                                }
                                placeholder="配置說明..."
                              />
                            </div>
                            <div className="flex items-center space-x-2 pt-2">
                              <Button size="sm" onClick={() => handleSave(config)}>
                                <Save className="h-4 w-4 mr-2" />
                                儲存
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={handleCancelEdit}
                              >
                                <X className="h-4 w-4 mr-2" />
                                取消
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <div className="mt-3 p-3 bg-muted/50 rounded-md">
                            {renderDisplayValue(config)}
                          </div>
                        )}
                      </div>
                    ))}
                  </CardContent>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* Audit Log Dialog */}
      <Dialog open={!!selectedConfigKey} onOpenChange={() => setSelectedConfigKey("")}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>配置變更記錄</DialogTitle>
            <DialogDescription>{selectedConfigKey} 的變更歷史</DialogDescription>
          </DialogHeader>
          <div className="max-h-96 overflow-y-auto">
            {auditLogs.length === 0 ? (
              <p className="text-center text-muted-foreground py-8">尚無變更記錄</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>操作</TableHead>
                    <TableHead>舊值</TableHead>
                    <TableHead>新值</TableHead>
                    <TableHead>操作者</TableHead>
                    <TableHead>時間</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {auditLogs.map((log, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <Badge
                          variant={
                            log.action === "CREATE"
                              ? "default"
                              : log.action === "UPDATE"
                                ? "secondary"
                                : "destructive"
                          }
                        >
                          {log.action === "CREATE"
                            ? "建立"
                            : log.action === "UPDATE"
                              ? "更新"
                              : "刪除"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground font-mono">
                          {log.old_value || "-"}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm font-mono">{log.new_value || "-"}</span>
                      </TableCell>
                      <TableCell>{log.user_name || `用戶 ${log.changed_by}`}</TableCell>
                      <TableCell>
                        {new Date(log.changed_at).toLocaleString("zh-TW")}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedConfigKey("")}>
              關閉
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
