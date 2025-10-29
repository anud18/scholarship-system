"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import apiClient, {
  AnnouncementCreate,
  AnnouncementUpdate,
  NotificationResponse,
} from "@/lib/api";
import {
  AlertCircle,
  Edit,
  MessageSquare,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";

interface User {
  id: string;
  nycu_id: string;
  name: string;
  email: string;
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  user_type?: "student" | "employee";
  status?: "在學" | "畢業" | "在職" | "退休";
  dept_code?: string;
  dept_name?: string;
  comment?: string;
  last_login_at?: string;
  created_at: string;
  updated_at: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
}

interface AnnouncementsPanelProps {
  user: User;
}

export function AnnouncementsPanel({ user }: AnnouncementsPanelProps) {
  const [announcements, setAnnouncements] = useState<NotificationResponse[]>(
    []
  );
  const [loadingAnnouncements, setLoadingAnnouncements] = useState(false);
  const [announcementsError, setAnnouncementsError] = useState<string | null>(
    null
  );
  const [showAnnouncementForm, setShowAnnouncementForm] = useState(false);
  const [editingAnnouncement, setEditingAnnouncement] =
    useState<NotificationResponse | null>(null);
  const [announcementForm, setAnnouncementForm] = useState<AnnouncementCreate>({
    title: "",
    message: "",
    notification_type: "info",
    priority: "normal",
  });
  const [announcementPagination, setAnnouncementPagination] = useState({
    page: 1,
    size: 10,
    total: 0,
  });

  const fetchAnnouncements = async () => {
    // 檢查用戶認證狀態
    if (!user || (user.role !== "admin" && user.role !== "super_admin")) {
      setAnnouncementsError("用戶未認證或不具有管理員權限");
      setLoadingAnnouncements(false);
      return;
    }

    setLoadingAnnouncements(true);
    setAnnouncementsError(null);

    try {
      const response = await apiClient.admin.getAllAnnouncements(
        announcementPagination.page,
        announcementPagination.size
      );

      if (response.success && response.data) {
        setAnnouncements(response.data.items || []);
        setAnnouncementPagination(prev => ({
          ...prev,
          total: response.data?.total || 0,
        }));
        // 清除錯誤信息
        setAnnouncementsError(null);
      } else {
        const errorMsg = response.message || "獲取公告失敗";
        setAnnouncementsError(errorMsg);
      }
    } catch (error) {
      const errorMsg =
        error instanceof Error ? error.message : "網絡錯誤，請檢查連接";
      setAnnouncementsError(errorMsg);
    } finally {
      setLoadingAnnouncements(false);
    }
  };

  const handleAnnouncementFormChange = (
    field: keyof AnnouncementCreate,
    value: string
  ) => {
    setAnnouncementForm(prev => ({ ...prev, [field]: value }));
  };

  const handleCreateAnnouncement = async () => {
    if (!announcementForm.title || !announcementForm.message) return;

    try {
      const response =
        await apiClient.admin.createAnnouncement(announcementForm);

      if (response.success) {
        setShowAnnouncementForm(false);
        setAnnouncementForm({
          title: "",
          message: "",
          notification_type: "info",
          priority: "normal",
        });
        fetchAnnouncements();
      } else {
        alert("創建公告失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "創建公告失敗: " + (error instanceof Error ? error.message : "網絡錯誤")
      );
    }
  };

  const handleUpdateAnnouncement = async () => {
    if (
      !editingAnnouncement ||
      !announcementForm.title ||
      !announcementForm.message
    )
      return;

    try {
      const response = await apiClient.admin.updateAnnouncement(
        editingAnnouncement.id,
        announcementForm as AnnouncementUpdate
      );

      if (response.success) {
        setEditingAnnouncement(null);
        setShowAnnouncementForm(false);
        setAnnouncementForm({
          title: "",
          message: "",
          notification_type: "info",
          priority: "normal",
        });
        fetchAnnouncements();
      } else {
        alert("更新公告失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "更新公告失敗: " + (error instanceof Error ? error.message : "網絡錯誤")
      );
    }
  };

  const handleDeleteAnnouncement = async (id: number) => {
    if (!confirm("確定要刪除此公告嗎？")) return;

    try {
      const response = await apiClient.admin.deleteAnnouncement(id);

      if (response.success) {
        fetchAnnouncements();
      } else {
        alert("刪除公告失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "刪除公告失敗: " + (error instanceof Error ? error.message : "網絡錯誤")
      );
    }
  };

  const handleEditAnnouncement = (announcement: NotificationResponse) => {
    setEditingAnnouncement(announcement);
    setAnnouncementForm({
      title: announcement.title,
      title_en: announcement.title_en,
      message: announcement.message,
      message_en: announcement.message_en,
      notification_type: announcement.notification_type as any,
      priority: announcement.priority as any,
      action_url: announcement.action_url,
      expires_at: announcement.expires_at,
      metadata: announcement.metadata,
    });
    setShowAnnouncementForm(true);
  };

  const resetAnnouncementForm = () => {
    setShowAnnouncementForm(false);
    setEditingAnnouncement(null);
    setAnnouncementForm({
      title: "",
      message: "",
      notification_type: "info",
      priority: "normal",
    });
  };

  // 載入系統公告
  useEffect(() => {
    // 檢查用戶是否已認證且具有管理員權限
    if (user && (user.role === "admin" || user.role === "super_admin")) {
      fetchAnnouncements();
    }
  }, [announcementPagination.page, announcementPagination.size, user]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">系統公告管理</h3>
        <Button
          onClick={() => setShowAnnouncementForm(true)}
          className="nycu-gradient text-white"
        >
          <Plus className="h-4 w-4 mr-1" />
          新增公告
        </Button>
      </div>

      {/* 公告表單 */}
      {showAnnouncementForm && (
        <Card className="border-nycu-blue-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageSquare className="h-5 w-5" />
              {editingAnnouncement ? "編輯公告" : "新增公告"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>公告標題 *</Label>
                <Input
                  value={announcementForm.title}
                  onChange={e =>
                    handleAnnouncementFormChange("title", e.target.value)
                  }
                  placeholder="輸入公告標題"
                  className="border-nycu-blue-200"
                />
              </div>
              <div className="space-y-2">
                <Label>英文標題</Label>
                <Input
                  value={announcementForm.title_en || ""}
                  onChange={e =>
                    handleAnnouncementFormChange("title_en", e.target.value)
                  }
                  placeholder="English title (optional)"
                  className="border-nycu-blue-200"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>公告內容 *</Label>
              <Textarea
                value={announcementForm.message}
                onChange={e =>
                  handleAnnouncementFormChange("message", e.target.value)
                }
                placeholder="輸入公告內容"
                rows={4}
                className="border-nycu-blue-200"
              />
            </div>

            <div className="space-y-2">
              <Label>英文內容</Label>
              <Textarea
                value={announcementForm.message_en || ""}
                onChange={e =>
                  handleAnnouncementFormChange("message_en", e.target.value)
                }
                placeholder="English message (optional)"
                rows={3}
                className="border-nycu-blue-200"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>公告類型</Label>
                <select
                  value={announcementForm.notification_type}
                  onChange={e =>
                    handleAnnouncementFormChange(
                      "notification_type",
                      e.target.value
                    )
                  }
                  className="w-full px-3 py-2 border border-nycu-blue-200 rounded-md"
                >
                  <option value="info">資訊</option>
                  <option value="warning">警告</option>
                  <option value="error">錯誤</option>
                  <option value="success">成功</option>
                  <option value="reminder">提醒</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>優先級</Label>
                <select
                  value={announcementForm.priority}
                  onChange={e =>
                    handleAnnouncementFormChange("priority", e.target.value)
                  }
                  className="w-full px-3 py-2 border border-nycu-blue-200 rounded-md"
                >
                  <option value="low">低</option>
                  <option value="normal">一般</option>
                  <option value="high">高</option>
                  <option value="urgent">緊急</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>行動連結</Label>
                <Input
                  value={announcementForm.action_url || ""}
                  onChange={e =>
                    handleAnnouncementFormChange(
                      "action_url",
                      e.target.value
                    )
                  }
                  placeholder="/path/to/action"
                  className="border-nycu-blue-200"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label>過期時間</Label>
              <Input
                type="datetime-local"
                value={
                  announcementForm.expires_at
                    ? new Date(announcementForm.expires_at)
                        .toISOString()
                        .slice(0, 16)
                    : ""
                }
                onChange={e =>
                  handleAnnouncementFormChange(
                    "expires_at",
                    e.target.value
                      ? new Date(e.target.value).toISOString()
                      : ""
                  )
                }
                className="border-nycu-blue-200"
              />
            </div>

            <div className="flex gap-2 pt-4">
              <Button
                onClick={
                  editingAnnouncement
                    ? handleUpdateAnnouncement
                    : handleCreateAnnouncement
                }
                disabled={
                  !announcementForm.title || !announcementForm.message
                }
                className="nycu-gradient text-white"
              >
                <Save className="h-4 w-4 mr-1" />
                {editingAnnouncement ? "更新公告" : "建立公告"}
              </Button>
              <Button variant="outline" onClick={resetAnnouncementForm}>
                取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 公告列表 */}
      <Card className="border-nycu-blue-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5" />
            系統公告列表
          </CardTitle>
        </CardHeader>
        <CardContent className="p-6">
          {loadingAnnouncements ? (
            <div className="flex items-center justify-center py-8">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                <span className="text-nycu-navy-600">載入公告中...</span>
              </div>
            </div>
          ) : announcementsError ? (
            <div className="text-center py-12">
              <AlertCircle className="h-16 w-16 mx-auto mb-4 text-red-400" />
              <p className="text-lg font-medium text-red-600 mb-2">
                載入公告失敗
              </p>
              <p className="text-sm text-gray-600 mb-4">
                {announcementsError}
              </p>
              <Button
                onClick={fetchAnnouncements}
                variant="outline"
                className="border-red-300 text-red-600 hover:bg-red-50"
              >
                重試
              </Button>
            </div>
          ) : announcements.length > 0 ? (
            <div className="space-y-6">
              {announcements.map(announcement => (
                <div
                  key={announcement.id}
                  className="p-5 border border-gray-200 rounded-lg hover:border-nycu-blue-300 transition-colors bg-white shadow-sm"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 pr-4">
                      <div className="flex items-center gap-2 mb-3">
                        <h4 className="font-semibold text-nycu-navy-800 text-lg">
                          {announcement.title}
                        </h4>
                        <Badge
                          variant={
                            announcement.notification_type === "error"
                              ? "destructive"
                              : announcement.notification_type === "warning"
                                ? "secondary"
                                : announcement.notification_type ===
                                    "success"
                                  ? "default"
                                  : "outline"
                          }
                        >
                          {announcement.notification_type}
                        </Badge>
                        <Badge variant="outline">
                          {announcement.priority}
                        </Badge>
                      </div>
                      <p className="text-gray-700 mb-3 leading-relaxed">
                        {announcement.message}
                      </p>
                      <div className="text-sm text-gray-500 bg-gray-50 p-2 rounded">
                        建立時間:{" "}
                        {new Date(announcement.created_at).toLocaleString(
                          "zh-TW",
                          {
                            year: "numeric",
                            month: "2-digit",
                            day: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                            hour12: false,
                          }
                        )}
                        {announcement.expires_at && (
                          <span className="ml-4">
                            過期時間:{" "}
                            {new Date(
                              announcement.expires_at
                            ).toLocaleString("zh-TW", {
                              year: "numeric",
                              month: "2-digit",
                              day: "2-digit",
                              hour: "2-digit",
                              minute: "2-digit",
                              second: "2-digit",
                              hour12: false,
                            })}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleEditAnnouncement(announcement)}
                        className="hover:bg-nycu-blue-50 hover:border-nycu-blue-300"
                      >
                        <Edit className="h-4 w-4 mr-1" />
                        編輯
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          handleDeleteAnnouncement(announcement.id)
                        }
                        className="hover:bg-red-50 hover:border-red-300 hover:text-red-600"
                      >
                        <Trash2 className="h-4 w-4 mr-1" />
                        刪除
                      </Button>
                    </div>
                  </div>
                </div>
              ))}

              {/* 分頁控制 */}
              {announcementPagination.total >
                announcementPagination.size && (
                <div className="flex items-center justify-between pt-6 border-t border-gray-200">
                  <div className="text-sm text-gray-600">
                    顯示第{" "}
                    {(announcementPagination.page - 1) *
                      announcementPagination.size +
                      1}{" "}
                    -{" "}
                    {Math.min(
                      announcementPagination.page *
                        announcementPagination.size,
                      announcementPagination.total
                    )}{" "}
                    項，共 {announcementPagination.total} 項公告
                  </div>
                  <div className="flex gap-3">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={announcementPagination.page <= 1}
                      onClick={() =>
                        setAnnouncementPagination(prev => ({
                          ...prev,
                          page: prev.page - 1,
                        }))
                      }
                      className="hover:bg-nycu-blue-50 hover:border-nycu-blue-300"
                    >
                      ← 上一頁
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={
                        announcementPagination.page *
                          announcementPagination.size >=
                        announcementPagination.total
                      }
                      onClick={() =>
                        setAnnouncementPagination(prev => ({
                          ...prev,
                          page: prev.page + 1,
                        }))
                      }
                      className="hover:bg-nycu-blue-50 hover:border-nycu-blue-300"
                    >
                      下一頁 →
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              <MessageSquare className="h-16 w-16 mx-auto mb-4 text-gray-300" />
              <p className="text-lg font-medium">尚無系統公告</p>
              <p className="text-sm mt-2 mb-4">
                點擊「新增公告」開始建立系統公告
              </p>
              <Button
                onClick={fetchAnnouncements}
                variant="outline"
                size="sm"
              >
                重新載入
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
