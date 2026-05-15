"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiClient, UserListResponse, UserStats, UserCreate } from "@/lib/api";
import { logger } from "@/lib/utils/logger";

export default function TestUsersPage() {
  const [users, setUsers] = useState<UserListResponse[]>([]);
  const [userStats, setUserStats] = useState<UserStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const testGetUsers = async () => {
    setLoading(true);
    setError(null);

    try {
      logger.debug("🧪 測試獲取用戶列表...");
      const response = await apiClient.users.getAll({ page: 1, size: 10 });
      logger.debug("📥 用戶列表響應:", response);

      if (response.success && response.data) {
        setUsers(response.data.items || []);
        logger.debug(
          "✅ 用戶列表獲取成功，數量:",
          response.data.items?.length || 0
        );
      } else {
        setError("獲取用戶失敗: " + (response.message || "未知錯誤"));
      }
    } catch (err) {
      logger.error("❌ 獲取用戶異常", { err: err });
      setError(
        "網絡錯誤: " + (err instanceof Error ? err.message : "未知錯誤")
      );
    } finally {
      setLoading(false);
    }
  };

  const testGetStats = async () => {
    try {
      logger.debug("🧪 測試獲取用戶統計...");
      const response = await apiClient.users.getStats();
      logger.debug("📥 用戶統計響應:", response);

      if (response.success && response.data) {
        setUserStats(response.data);
        logger.debug("✅ 用戶統計獲取成功");
      } else {
        setError("獲取統計失敗: " + (response.message || "未知錯誤"));
      }
    } catch (err) {
      logger.error("❌ 獲取統計異常", { err: err });
      setError(
        "網絡錯誤: " + (err instanceof Error ? err.message : "未知錯誤")
      );
    }
  };

  const testCreateUser = async () => {
    try {
      logger.debug("🧪 測試創建用戶...");
      const newUser: UserCreate = {
        nycu_id: `test-${Date.now()}`,
        name: "測試用戶",
        email: `test${Date.now()}@example.com`,
        role: "student",
        user_type: "student",
        status: "在學",
        dept_code: "5802",
        dept_name: "校務資訊組",
        comment: "Test user",
        raw_data: {
          chinese_name: "測試用戶",
          english_name: "Test User",
        },
      };

      const response = await apiClient.users.create(newUser);
      logger.debug("📥 創建用戶響應:", response);

      if (response.success) {
        logger.debug("✅ 用戶創建成功");
        testGetUsers(); // 重新獲取用戶列表
      } else {
        setError("創建用戶失敗: " + (response.message || "未知錯誤"));
      }
    } catch (err) {
      logger.error("❌ 創建用戶異常", { err: err });
      setError(
        "網絡錯誤: " + (err instanceof Error ? err.message : "未知錯誤")
      );
    }
  };

  useEffect(() => {
    testGetUsers();
    testGetStats();
  }, []);

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">用戶管理 API 測試</h1>

      {error && (
        <Card className="mb-6 border-red-200 bg-red-50">
          <CardContent className="pt-4">
            <p className="text-red-600">{error}</p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6">
        {/* 統計信息 */}
        <Card>
          <CardHeader>
            <CardTitle>用戶統計</CardTitle>
          </CardHeader>
          <CardContent>
            {userStats ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-sm text-gray-600">總用戶數</p>
                  <p className="text-2xl font-bold">{userStats.total_users}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">在職用戶</p>
                  <p className="text-2xl font-bold">{userStats.status_distribution?.['在職'] || 0}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">學生用戶</p>
                  <p className="text-2xl font-bold">
                    {userStats.role_distribution?.student || 0}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-600">本月新增</p>
                  <p className="text-2xl font-bold">
                    {userStats.recent_registrations}
                  </p>
                </div>
              </div>
            ) : (
              <p>載入中...</p>
            )}
          </CardContent>
        </Card>

        {/* 操作按鈕 */}
        <Card>
          <CardHeader>
            <CardTitle>測試操作</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-4">
              <Button onClick={testGetUsers} disabled={loading}>
                {loading ? "載入中..." : "獲取用戶列表"}
              </Button>
              <Button onClick={testGetStats} variant="outline">
                獲取統計信息
              </Button>
              <Button onClick={testCreateUser} variant="secondary">
                創建測試用戶
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* 用戶列表 */}
        <Card>
          <CardHeader>
            <CardTitle>用戶列表 ({users.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {users.length > 0 ? (
              <div className="space-y-4">
                {users.map(user => (
                  <div key={user.id} className="p-4 border rounded-lg">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div>
                        <p className="font-medium">{user.name}</p>
                        <p className="text-sm text-gray-600">{user.email}</p>
                        <p className="text-sm text-gray-600">@{user.nycu_id}</p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-600">
                          角色: {user.role}
                        </p>
                        <p className="text-sm text-gray-600">
                          狀態: {user.status}
                        </p>
                        {user.raw_data?.chinese_name && (
                          <p className="text-sm text-gray-600">
                            中文姓名: {user.raw_data.chinese_name}
                          </p>
                        )}
                      </div>
                      <div>
                        <p className="text-sm text-gray-600">
                          註冊:{" "}
                          {new Date(user.created_at).toLocaleDateString(
                            "zh-TW"
                          )}
                        </p>
                        <p className="text-sm text-gray-600">
                          最後登入:{" "}
                          {user.last_login_at
                            ? new Date(user.last_login_at).toLocaleDateString(
                                "zh-TW"
                              )
                            : "從未登入"}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500">無用戶數據</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
