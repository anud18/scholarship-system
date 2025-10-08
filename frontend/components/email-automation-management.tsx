"use client";

import { useEffect, useState } from "react";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Edit,
  Trash2,
  Loader2,
  Mail,
  Clock,
  Zap,
  AlertCircle,
} from "lucide-react";
import { apiClient } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

interface EmailAutomationRule {
  id: number;
  name: string;
  description?: string;
  trigger_event: string;
  template_key: string;
  delay_hours: number;
  condition_query?: string;
  is_active: boolean;
  created_by_user_id?: number;
  created_at: string;
  updated_at: string;
}

interface TriggerEvent {
  value: string;
  label: string;
  description: string;
}

interface EmailTemplate {
  key: string;
  label: string;
  subject_template?: string;
}

export function EmailAutomationManagement() {
  const { toast } = useToast();
  const [rules, setRules] = useState<EmailAutomationRule[]>([]);
  const [triggerEvents, setTriggerEvents] = useState<TriggerEvent[]>([]);
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Dialog states
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedRule, setSelectedRule] = useState<EmailAutomationRule | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    trigger_event: "",
    template_key: "",
    delay_hours: 0,
    condition_query: "",
    is_active: true,
  });

  // Fetch data on mount
  useEffect(() => {
    fetchRules();
    fetchTriggerEvents();
    fetchEmailTemplates();
  }, []);

  const fetchRules = async () => {
    try {
      setIsLoading(true);
      const response = await apiClient.emailAutomation.getRules();
      if (response.success && response.data) {
        setRules(response.data);
      }
    } catch (error: any) {
      toast({
        title: "錯誤",
        description: error.message || "無法載入自動化規則",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const fetchTriggerEvents = async () => {
    try {
      const response = await apiClient.emailAutomation.getTriggerEvents();
      if (response.success && response.data) {
        setTriggerEvents(response.data);
      }
    } catch (error: any) {
      console.error("Failed to fetch trigger events:", error);
    }
  };

  const fetchEmailTemplates = async () => {
    try {
      const response = await apiClient.admin.getEmailTemplatesBySendingType();
      if (response.success && response.data) {
        // Use subject_template from database as label
        const templates = response.data.map((t: any) => ({
          key: t.key,
          label: t.subject_template || t.key, // Use subject as label, fallback to key
          subject_template: t.subject_template,
        }));
        setEmailTemplates(templates);
      }
    } catch (error: any) {
      console.error("Failed to fetch email templates:", error);
    }
  };

  const handleCreate = () => {
    setFormData({
      name: "",
      description: "",
      trigger_event: "",
      template_key: "",
      delay_hours: 0,
      condition_query: "",
      is_active: true,
    });
    setIsCreateDialogOpen(true);
  };

  const handleEdit = (rule: EmailAutomationRule) => {
    setSelectedRule(rule);
    setFormData({
      name: rule.name,
      description: rule.description || "",
      trigger_event: rule.trigger_event,
      template_key: rule.template_key,
      delay_hours: rule.delay_hours,
      condition_query: rule.condition_query || "",
      is_active: rule.is_active,
    });
    setIsEditDialogOpen(true);
  };

  const handleDelete = (rule: EmailAutomationRule) => {
    setSelectedRule(rule);
    setIsDeleteDialogOpen(true);
  };

  const handleSubmitCreate = async () => {
    if (!formData.name || !formData.trigger_event || !formData.template_key) {
      toast({
        title: "驗證錯誤",
        description: "請填寫所有必填欄位",
        variant: "destructive",
      });
      return;
    }

    try {
      setIsSubmitting(true);
      const response = await apiClient.emailAutomation.createRule(formData);
      if (response.success) {
        toast({
          title: "成功",
          description: "自動化規則已創建",
        });
        setIsCreateDialogOpen(false);
        fetchRules();
      }
    } catch (error: any) {
      toast({
        title: "錯誤",
        description: error.message || "創建規則失敗",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmitEdit = async () => {
    if (!selectedRule) return;

    if (!formData.name || !formData.trigger_event || !formData.template_key) {
      toast({
        title: "驗證錯誤",
        description: "請填寫所有必填欄位",
        variant: "destructive",
      });
      return;
    }

    try {
      setIsSubmitting(true);
      const response = await apiClient.emailAutomation.updateRule(
        selectedRule.id,
        formData
      );
      if (response.success) {
        toast({
          title: "成功",
          description: "自動化規則已更新",
        });
        setIsEditDialogOpen(false);
        fetchRules();
      }
    } catch (error: any) {
      toast({
        title: "錯誤",
        description: error.message || "更新規則失敗",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!selectedRule) return;

    try {
      setIsSubmitting(true);
      const response = await apiClient.emailAutomation.deleteRule(selectedRule.id);
      if (response.success) {
        toast({
          title: "成功",
          description: "自動化規則已刪除",
        });
        setIsDeleteDialogOpen(false);
        fetchRules();
      }
    } catch (error: any) {
      toast({
        title: "錯誤",
        description: error.message || "刪除規則失敗",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToggleActive = async (rule: EmailAutomationRule) => {
    try {
      const response = await apiClient.emailAutomation.toggleRule(rule.id);
      if (response.success) {
        toast({
          title: "成功",
          description: rule.is_active ? "規則已停用" : "規則已啟用",
        });
        fetchRules();
      }
    } catch (error: any) {
      toast({
        title: "錯誤",
        description: error.message || "切換規則狀態失敗",
        variant: "destructive",
      });
    }
  };

  const getTriggerEventLabel = (value: string) => {
    const event = triggerEvents.find((e) => e.value === value);
    return event?.label || value;
  };

  const getTemplateLabel = (key: string) => {
    const template = emailTemplates.find((t) => t.key === key);
    return template?.label || key;
  };

  return (
    <Card className="academic-card border-nycu-blue-200">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
              <Zap className="h-5 w-5 text-nycu-blue-600" />
              郵件自動化規則
            </CardTitle>
            <CardDescription>
              設定觸發條件自動發送郵件通知
            </CardDescription>
          </div>
          <Button
            onClick={handleCreate}
            className="bg-nycu-blue-600 hover:bg-nycu-blue-700"
          >
            <Plus className="h-4 w-4 mr-2" />
            新增規則
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-nycu-blue-600" />
          </div>
        ) : rules.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 text-gray-400" />
            <p>尚未設定任何自動化規則</p>
            <p className="text-sm mt-2">點擊「新增規則」開始設定</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>規則名稱</TableHead>
                <TableHead>觸發事件</TableHead>
                <TableHead>郵件模板</TableHead>
                <TableHead>延遲時間</TableHead>
                <TableHead>狀態</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell>
                    <div>
                      <div className="font-medium text-nycu-navy-800">
                        {rule.name}
                      </div>
                      {rule.description && (
                        <div className="text-sm text-gray-500">
                          {rule.description}
                        </div>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="border-nycu-blue-300">
                      {getTriggerEventLabel(rule.trigger_event)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-gray-400" />
                      <span className="text-sm">
                        {getTemplateLabel(rule.template_key)}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-gray-400" />
                      <span className="text-sm">
                        {rule.delay_hours === 0
                          ? "立即"
                          : `${rule.delay_hours} 小時後`}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={rule.is_active}
                      onCheckedChange={() => handleToggleActive(rule)}
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleEdit(rule)}
                      >
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(rule)}
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {/* Create Dialog */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>新增自動化規則</DialogTitle>
            <DialogDescription>
              設定郵件自動發送的觸發條件和模板
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">規則名稱 *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                placeholder="例如：申請提交通知"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">描述</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                placeholder="規則的詳細說明（可選）"
                rows={2}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="trigger_event">觸發事件 *</Label>
                <Select
                  value={formData.trigger_event}
                  onValueChange={(value) =>
                    setFormData({ ...formData, trigger_event: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="選擇觸發事件" />
                  </SelectTrigger>
                  <SelectContent>
                    {triggerEvents.map((event) => (
                      <SelectItem key={event.value} value={event.value}>
                        <div>
                          <div>{event.label}</div>
                          <div className="text-xs text-gray-500">
                            {event.description}
                          </div>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="template_key">郵件模板 *</Label>
                <Select
                  value={formData.template_key}
                  onValueChange={(value) =>
                    setFormData({ ...formData, template_key: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="選擇郵件模板" />
                  </SelectTrigger>
                  <SelectContent>
                    {emailTemplates.map((template) => (
                      <SelectItem key={template.key} value={template.key}>
                        {template.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="delay_hours">延遲時間（小時）</Label>
              <Input
                id="delay_hours"
                type="number"
                min="0"
                value={formData.delay_hours}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    delay_hours: parseInt(e.target.value) || 0,
                  })
                }
                placeholder="0"
              />
              <p className="text-xs text-gray-500">
                設定為 0 表示立即發送，大於 0 表示延遲指定小時後發送
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="condition_query">條件查詢（進階）</Label>
              <Textarea
                id="condition_query"
                value={formData.condition_query}
                onChange={(e) =>
                  setFormData({ ...formData, condition_query: e.target.value })
                }
                placeholder="SQL 查詢條件（可選）"
                rows={3}
              />
              <p className="text-xs text-gray-500">
                進階功能：自訂 SQL 條件來過濾觸發對象
              </p>
            </div>
            <div className="flex items-center space-x-2">
              <Switch
                id="is_active"
                checked={formData.is_active}
                onCheckedChange={(checked) =>
                  setFormData({ ...formData, is_active: checked })
                }
              />
              <Label htmlFor="is_active">啟用規則</Label>
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
              onClick={handleSubmitCreate}
              disabled={isSubmitting}
              className="bg-nycu-blue-600 hover:bg-nycu-blue-700"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  創建中...
                </>
              ) : (
                "創建規則"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>編輯自動化規則</DialogTitle>
            <DialogDescription>
              修改郵件自動發送的觸發條件和模板
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">規則名稱 *</Label>
              <Input
                id="edit-name"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                placeholder="例如：申請提交通知"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-description">描述</Label>
              <Textarea
                id="edit-description"
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                placeholder="規則的詳細說明（可選）"
                rows={2}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="edit-trigger_event">觸發事件 *</Label>
                <Select
                  value={formData.trigger_event}
                  onValueChange={(value) =>
                    setFormData({ ...formData, trigger_event: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="選擇觸發事件" />
                  </SelectTrigger>
                  <SelectContent>
                    {triggerEvents.map((event) => (
                      <SelectItem key={event.value} value={event.value}>
                        <div>
                          <div>{event.label}</div>
                          <div className="text-xs text-gray-500">
                            {event.description}
                          </div>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-template_key">郵件模板 *</Label>
                <Select
                  value={formData.template_key}
                  onValueChange={(value) =>
                    setFormData({ ...formData, template_key: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="選擇郵件模板" />
                  </SelectTrigger>
                  <SelectContent>
                    {emailTemplates.map((template) => (
                      <SelectItem key={template.key} value={template.key}>
                        {template.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-delay_hours">延遲時間（小時）</Label>
              <Input
                id="edit-delay_hours"
                type="number"
                min="0"
                value={formData.delay_hours}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    delay_hours: parseInt(e.target.value) || 0,
                  })
                }
                placeholder="0"
              />
              <p className="text-xs text-gray-500">
                設定為 0 表示立即發送，大於 0 表示延遲指定小時後發送
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-condition_query">條件查詢（進階）</Label>
              <Textarea
                id="edit-condition_query"
                value={formData.condition_query}
                onChange={(e) =>
                  setFormData({ ...formData, condition_query: e.target.value })
                }
                placeholder="SQL 查詢條件（可選）"
                rows={3}
              />
              <p className="text-xs text-gray-500">
                進階功能：自訂 SQL 條件來過濾觸發對象
              </p>
            </div>
            <div className="flex items-center space-x-2">
              <Switch
                id="edit-is_active"
                checked={formData.is_active}
                onCheckedChange={(checked) =>
                  setFormData({ ...formData, is_active: checked })
                }
              />
              <Label htmlFor="edit-is_active">啟用規則</Label>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsEditDialogOpen(false)}
            >
              取消
            </Button>
            <Button
              onClick={handleSubmitEdit}
              disabled={isSubmitting}
              className="bg-nycu-blue-600 hover:bg-nycu-blue-700"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  更新中...
                </>
              ) : (
                "更新規則"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>確認刪除</AlertDialogTitle>
            <AlertDialogDescription>
              確定要刪除規則「{selectedRule?.name}」嗎？此操作無法復原。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              disabled={isSubmitting}
              className="bg-red-600 hover:bg-red-700"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  刪除中...
                </>
              ) : (
                "刪除"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
