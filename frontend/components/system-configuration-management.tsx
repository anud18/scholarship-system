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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Plus,
  Edit2,
  Trash2,
  Eye,
  EyeOff,
  Save,
  X,
  History,
  AlertTriangle,
  CheckCircle,
  Settings,
  Shield,
  Mail,
  Database,
  Key,
  FileText,
  Bell,
  Camera,
  Link,
} from "lucide-react";
import {
  apiClient,
  SystemConfiguration,
  SystemConfigurationCreate,
  SystemConfigurationUpdate,
} from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";

const categoryIcons = {
  FEATURES: Settings,
  SECURITY: Shield,
  EMAIL: Mail,
  DATABASE: Database,
  API_KEYS: Key,
  FILE_STORAGE: FileText,
  NOTIFICATION: Bell,
  OCR: Camera,
  INTEGRATIONS: Link,
};

const categoryLabels = {
  FEATURES: "功能設定",
  SECURITY: "安全設定",
  EMAIL: "電子郵件設定",
  DATABASE: "資料庫設定",
  API_KEYS: "API 金鑰",
  FILE_STORAGE: "檔案儲存",
  NOTIFICATION: "通知設定",
  OCR: "OCR 設定",
  INTEGRATIONS: "第三方整合",
};

const dataTypeLabels = {
  STRING: "字串",
  INTEGER: "整數",
  FLOAT: "浮點數",
  BOOLEAN: "布林值",
  JSON: "JSON 物件",
};

export default function SystemConfigurationManagement() {
  const { user } = useAuth();
  const [configurations, setConfigurations] = useState<SystemConfiguration[]>(
    []
  );
  const [categories, setCategories] = useState<string[]>([]);
  const [dataTypes, setDataTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [showSensitive, setShowSensitive] = useState(false);
  const [editingConfig, setEditingConfig] =
    useState<SystemConfiguration | null>(null);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [selectedConfigKey, setSelectedConfigKey] = useState<string>("");

  // Form states
  const [formData, setFormData] = useState<SystemConfigurationCreate>({
    key: "",
    value: "",
    category: "FEATURES",
    data_type: "STRING",
    is_sensitive: false,
    description: "",
    validation_regex: "",
  });

  const [updateFormData, setUpdateFormData] =
    useState<SystemConfigurationUpdate>({
      value: "",
      category: "FEATURES",
      data_type: "STRING",
      is_sensitive: false,
      description: "",
      validation_regex: "",
    });

  const loadConfigurations = async () => {
    try {
      setLoading(true);
      const response = await apiClient.system.getConfigurations(
        selectedCategory,
        showSensitive
      );
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

  const loadMetadata = async () => {
    try {
      const [categoriesResponse, dataTypesResponse] = await Promise.all([
        apiClient.system.getCategories(),
        apiClient.system.getDataTypes(),
      ]);

      if (categoriesResponse.success && categoriesResponse.data) {
        setCategories(categoriesResponse.data);
      }

      if (dataTypesResponse.success && dataTypesResponse.data) {
        setDataTypes(dataTypesResponse.data);
      }
    } catch (err) {
      console.error("Error loading metadata:", err);
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

  useEffect(() => {
    loadConfigurations();
    loadMetadata();
  }, [selectedCategory, showSensitive]);

  const handleCreate = async () => {
    try {
      const response = await apiClient.system.createConfiguration(formData);
      if (response.success) {
        setIsCreateDialogOpen(false);
        setFormData({
          key: "",
          value: "",
          category: "FEATURES",
          data_type: "STRING",
          is_sensitive: false,
          description: "",
          validation_regex: "",
        });
        loadConfigurations();
      } else {
        setError(response.message || "創建配置失敗");
      }
    } catch (err) {
      setError("創建配置時發生錯誤");
      console.error("Error creating configuration:", err);
    }
  };

  const handleUpdate = async () => {
    if (!editingConfig) return;

    try {
      const response = await apiClient.system.updateConfiguration(
        editingConfig.key,
        updateFormData
      );
      if (response.success) {
        setIsEditDialogOpen(false);
        setEditingConfig(null);
        loadConfigurations();
      } else {
        setError(response.message || "更新配置失敗");
      }
    } catch (err) {
      setError("更新配置時發生錯誤");
      console.error("Error updating configuration:", err);
    }
  };

  const handleDelete = async () => {
    if (!editingConfig) return;

    try {
      const response = await apiClient.system.deleteConfiguration(
        editingConfig.key
      );
      if (response.success) {
        setIsDeleteDialogOpen(false);
        setEditingConfig(null);
        loadConfigurations();
      } else {
        setError(response.message || "刪除配置失敗");
      }
    } catch (err) {
      setError("刪除配置時發生錯誤");
      console.error("Error deleting configuration:", err);
    }
  };

  const openEditDialog = (config: SystemConfiguration) => {
    setEditingConfig(config);
    setUpdateFormData({
      value: config.value,
      category: config.category,
      data_type: config.data_type,
      is_sensitive: config.is_sensitive,
      description: config.description || "",
      validation_regex: config.validation_regex || "",
    });
    setIsEditDialogOpen(true);
  };

  const openDeleteDialog = (config: SystemConfiguration) => {
    setEditingConfig(config);
    setIsDeleteDialogOpen(true);
  };

  const openAuditDialog = (configKey: string) => {
    setSelectedConfigKey(configKey);
    loadAuditLogs(configKey);
  };

  const filteredConfigurations = configurations.filter(
    config => !selectedCategory || config.category === selectedCategory
  );

  const groupedConfigurations = categories.reduce(
    (acc, category) => {
      acc[category] = filteredConfigurations.filter(
        config => config.category === category
      );
      return acc;
    },
    {} as Record<string, SystemConfiguration[]>
  );

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
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">系統配置管理</h1>
          <p className="text-muted-foreground">管理系統配置參數和設定</p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <Label htmlFor="show-sensitive">顯示敏感資料</Label>
            <Switch
              id="show-sensitive"
              checked={showSensitive}
              onCheckedChange={setShowSensitive}
            />
          </div>
          <Dialog
            open={isCreateDialogOpen}
            onOpenChange={setIsCreateDialogOpen}
          >
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                新增配置
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>新增系統配置</DialogTitle>
                <DialogDescription>建立新的系統配置項目</DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="key">配置鍵名 *</Label>
                    <Input
                      id="key"
                      value={formData.key}
                      onChange={e =>
                        setFormData({ ...formData, key: e.target.value })
                      }
                      placeholder="例如：smtp_host"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="category">類別 *</Label>
                    <Select
                      value={formData.category}
                      onValueChange={(value: any) =>
                        setFormData({ ...formData, category: value })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {categories.map(category => (
                          <SelectItem key={category} value={category}>
                            {categoryLabels[
                              category as keyof typeof categoryLabels
                            ] || category}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="data_type">資料類型 *</Label>
                    <Select
                      value={formData.data_type}
                      onValueChange={(value: any) =>
                        setFormData({ ...formData, data_type: value })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {dataTypes.map(type => (
                          <SelectItem key={type} value={type}>
                            {dataTypeLabels[
                              type as keyof typeof dataTypeLabels
                            ] || type}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="is_sensitive">敏感資料</Label>
                    <div className="flex items-center space-x-2 pt-2">
                      <Switch
                        id="is_sensitive"
                        checked={formData.is_sensitive}
                        onCheckedChange={checked =>
                          setFormData({ ...formData, is_sensitive: checked })
                        }
                      />
                      <span className="text-sm text-muted-foreground">
                        {formData.is_sensitive ? "是" : "否"}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="value">配置值 *</Label>
                  <Textarea
                    id="value"
                    value={formData.value}
                    onChange={e =>
                      setFormData({ ...formData, value: e.target.value })
                    }
                    placeholder="輸入配置值"
                    rows={3}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">描述</Label>
                  <Textarea
                    id="description"
                    value={formData.description}
                    onChange={e =>
                      setFormData({ ...formData, description: e.target.value })
                    }
                    placeholder="配置說明"
                    rows={2}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="validation_regex">驗證正則表達式</Label>
                  <Input
                    id="validation_regex"
                    value={formData.validation_regex}
                    onChange={e =>
                      setFormData({
                        ...formData,
                        validation_regex: e.target.value,
                      })
                    }
                    placeholder="例如：^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setIsCreateDialogOpen(false)}
                >
                  取消
                </Button>
                <Button
                  onClick={handleCreate}
                  disabled={!formData.key || !formData.value}
                >
                  建立
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="configurations" className="space-y-4">
        <TabsList>
          <TabsTrigger value="configurations">配置管理</TabsTrigger>
          <TabsTrigger value="categories">分類瀏覽</TabsTrigger>
        </TabsList>

        <TabsContent value="configurations" className="space-y-4">
          <div className="flex items-center space-x-4">
            <Select
              value={selectedCategory}
              onValueChange={setSelectedCategory}
            >
              <SelectTrigger className="w-48">
                <SelectValue placeholder="選擇類別" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">所有類別</SelectItem>
                {categories.map(category => (
                  <SelectItem key={category} value={category}>
                    {categoryLabels[category as keyof typeof categoryLabels] ||
                      category}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={loadConfigurations}>
              重新載入
            </Button>
          </div>

          {loading ? (
            <div className="text-center py-8">載入中...</div>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>配置列表</CardTitle>
                <CardDescription>
                  共 {filteredConfigurations.length} 項配置
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>鍵名</TableHead>
                      <TableHead>值</TableHead>
                      <TableHead>類別</TableHead>
                      <TableHead>類型</TableHead>
                      <TableHead>狀態</TableHead>
                      <TableHead>操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredConfigurations.map(config => {
                      const CategoryIcon =
                        categoryIcons[
                          config.category as keyof typeof categoryIcons
                        ];
                      return (
                        <TableRow key={config.id}>
                          <TableCell className="font-medium">
                            <div className="flex items-center space-x-2">
                              {CategoryIcon && (
                                <CategoryIcon className="h-4 w-4" />
                              )}
                              <span>{config.key}</span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center space-x-2">
                              <span className="max-w-xs truncate">
                                {config.is_sensitive && !showSensitive
                                  ? "***"
                                  : config.value}
                              </span>
                              {config.is_sensitive && (
                                <Badge variant="secondary">
                                  <Shield className="h-3 w-3 mr-1" />
                                  敏感
                                </Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">
                              {categoryLabels[
                                config.category as keyof typeof categoryLabels
                              ] || config.category}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary">
                              {dataTypeLabels[
                                config.data_type as keyof typeof dataTypeLabels
                              ] || config.data_type}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center space-x-1">
                              <CheckCircle className="h-4 w-4 text-green-500" />
                              <span className="text-sm">活躍</span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center space-x-2">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => openEditDialog(config)}
                              >
                                <Edit2 className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => openDeleteDialog(config)}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => openAuditDialog(config.key)}
                              >
                                <History className="h-4 w-4" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="categories" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {categories.map(category => {
              const configs = groupedConfigurations[category] || [];
              const CategoryIcon =
                categoryIcons[category as keyof typeof categoryIcons];
              return (
                <Card key={category}>
                  <CardHeader>
                    <CardTitle className="flex items-center space-x-2">
                      {CategoryIcon && <CategoryIcon className="h-5 w-5" />}
                      <span>
                        {categoryLabels[
                          category as keyof typeof categoryLabels
                        ] || category}
                      </span>
                    </CardTitle>
                    <CardDescription>{configs.length} 項配置</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {configs.slice(0, 5).map(config => (
                        <div
                          key={config.id}
                          className="flex justify-between items-center"
                        >
                          <span className="text-sm truncate">{config.key}</span>
                          <div className="flex items-center space-x-1">
                            {config.is_sensitive && (
                              <Shield className="h-3 w-3 text-orange-500" />
                            )}
                            <Badge variant="outline" className="text-xs">
                              {
                                dataTypeLabels[
                                  config.data_type as keyof typeof dataTypeLabels
                                ]
                              }
                            </Badge>
                          </div>
                        </div>
                      ))}
                      {configs.length > 5 && (
                        <div className="text-xs text-muted-foreground">
                          還有 {configs.length - 5} 項...
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </TabsContent>
      </Tabs>

      {/* Edit Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>編輯配置</DialogTitle>
            <DialogDescription>
              修改 {editingConfig?.key} 的設定
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="edit-category">類別</Label>
                <Select
                  value={updateFormData.category}
                  onValueChange={(value: any) =>
                    setUpdateFormData({ ...updateFormData, category: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {categories.map(category => (
                      <SelectItem key={category} value={category}>
                        {categoryLabels[
                          category as keyof typeof categoryLabels
                        ] || category}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-data_type">資料類型</Label>
                <Select
                  value={updateFormData.data_type}
                  onValueChange={(value: any) =>
                    setUpdateFormData({ ...updateFormData, data_type: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {dataTypes.map(type => (
                      <SelectItem key={type} value={type}>
                        {dataTypeLabels[type as keyof typeof dataTypeLabels] ||
                          type}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-is_sensitive">敏感資料</Label>
              <div className="flex items-center space-x-2 pt-2">
                <Switch
                  id="edit-is_sensitive"
                  checked={updateFormData.is_sensitive}
                  onCheckedChange={checked =>
                    setUpdateFormData({
                      ...updateFormData,
                      is_sensitive: checked,
                    })
                  }
                />
                <span className="text-sm text-muted-foreground">
                  {updateFormData.is_sensitive ? "是" : "否"}
                </span>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-value">配置值</Label>
              <Textarea
                id="edit-value"
                value={updateFormData.value}
                onChange={e =>
                  setUpdateFormData({
                    ...updateFormData,
                    value: e.target.value,
                  })
                }
                rows={3}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-description">描述</Label>
              <Textarea
                id="edit-description"
                value={updateFormData.description}
                onChange={e =>
                  setUpdateFormData({
                    ...updateFormData,
                    description: e.target.value,
                  })
                }
                rows={2}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-validation_regex">驗證正則表達式</Label>
              <Input
                id="edit-validation_regex"
                value={updateFormData.validation_regex}
                onChange={e =>
                  setUpdateFormData({
                    ...updateFormData,
                    validation_regex: e.target.value,
                  })
                }
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsEditDialogOpen(false)}
            >
              取消
            </Button>
            <Button onClick={handleUpdate}>
              <Save className="h-4 w-4 mr-2" />
              儲存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>刪除配置</DialogTitle>
            <DialogDescription>
              確定要刪除配置 "{editingConfig?.key}" 嗎？此操作無法復原。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
            >
              取消
            </Button>
            <Button variant="destructive" onClick={handleDelete}>
              <Trash2 className="h-4 w-4 mr-2" />
              刪除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Audit Log Dialog */}
      <Dialog
        open={!!selectedConfigKey}
        onOpenChange={() => setSelectedConfigKey("")}
      >
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>配置變更記錄</DialogTitle>
            <DialogDescription>
              {selectedConfigKey} 的變更歷史
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-96 overflow-y-auto">
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
                      <span className="text-sm text-muted-foreground">
                        {log.old_value || "-"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">{log.new_value || "-"}</span>
                    </TableCell>
                    <TableCell>
                      {log.user_name || `用戶 ${log.changed_by}`}
                    </TableCell>
                    <TableCell>
                      {new Date(log.changed_at).toLocaleString("zh-TW")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
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
