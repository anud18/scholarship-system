"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/hooks/use-auth";
import { apiClient } from "@/lib/api";
import type { UserStats, UserCreate as UserCreateType } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Plus, Upload, Users, AlertCircle, Edit } from "lucide-react";
import { UserEditModal } from "@/components/user-edit-modal";

interface UserListResponse {
  id: number;
  nycu_id: string;
  name: string;
  email: string;
  role: string;
  college_code?: string;
  dept_code?: string;
  dept_name?: string;
  username?: string;
  full_name?: string;
  chinese_name?: string;
  english_name?: string;
  user_type?: string;
  status?: string;
  comment?: string;
  created_at: string;
  last_login_at?: string;
  student_no?: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
  };
}

// Using UserStats from @/lib/api

// Extend imported UserCreate with form-specific fields
// Note: System uses SSO-only authentication via NYCU Portal - no password authentication
interface UserCreateForm extends UserCreateType {
  student_no?: string;
}

interface ScholarshipPermission {
  id: number;
  user_id: number;
  scholarship_id: number;
  scholarship_name: string;
  scholarship_name_en?: string;
  comment?: string;
}

interface Scholarship {
  id: number;
  code: string;
  name: string;
  name_en?: string;
  category: string;
  status: string;
}

export function UserPermissionManagement() {
  const { user } = useAuth();

  // User management states
  const [users, setUsers] = useState<UserListResponse[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [userStats, setUserStats] = useState<UserStats>({
    total_users: 0,
    role_distribution: {},
    user_type_distribution: {},
    status_distribution: {},
    recent_registrations: 0,
  });
  const [showUserForm, setShowUserForm] = useState(false);
  const [editingUser, setEditingUser] = useState<UserListResponse | null>(null);
  // User form state - SSO authentication system (no password-based auth)
  // User details (name, email) are auto-populated on first SSO login via NYCU Portal
  const [userForm, setUserForm] = useState<UserCreateForm>({
    nycu_id: "",
    email: "",
    name: "",
    role: "college",
    student_no: "",
  });
  const [userPagination, setUserPagination] = useState({
    page: 1,
    size: 10,
    total: 0,
  });
  const [userSearch, setUserSearch] = useState("");
  const [userRoleFilter, setUserRoleFilter] = useState("");
  const [userFormLoading, setUserFormLoading] = useState(false);

  // Scholarship permissions
  const [scholarshipPermissions, setScholarshipPermissions] = useState<
    ScholarshipPermission[]
  >([]);
  const [loadingPermissions, setLoadingPermissions] = useState(false);
  const [availableScholarships, setAvailableScholarships] = useState<
    Scholarship[]
  >([]);

  // Academy list for displaying college names
  const [academies, setAcademies] = useState<
    Array<{ id: number; code: string; name: string }>
  >([]);

  // Fetch users
  const fetchUsers = async () => {
    setLoadingUsers(true);
    setUsersError(null);

    try {
      let rolesParam = "college,admin,super_admin,professor";
      if (user?.role === "admin") {
        rolesParam = "college,admin,professor";
      }
      rolesParam = rolesParam
        .split(",")
        .map((role) => role.trim())
        .join(",");

      const params: any = {
        page: userPagination.page,
        size: userPagination.size,
        roles: rolesParam,
      };

      if (userSearch) params.search = userSearch;
      if (userRoleFilter) params.role = userRoleFilter;

      const response = await apiClient.users.getAll(params);

      if (response.success && response.data) {
        const managementUsers = response.data.items || [];
        const sortedUsers = managementUsers.sort((a, b) => {
          const roleOrder = {
            super_admin: 1,
            admin: 2,
            college: 3,
            professor: 4,
          };
          const aOrder = roleOrder[a.role as keyof typeof roleOrder] || 999;
          const bOrder = roleOrder[b.role as keyof typeof roleOrder] || 999;
          return aOrder - bOrder;
        });

        setUsers(sortedUsers);
        setUserPagination((prev) => ({
          ...prev,
          total: sortedUsers.length,
        }));
      } else {
        const errorMsg = response.message || "獲取使用者失敗";
        setUsersError(errorMsg);
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : "網絡錯誤";
      setUsersError(errorMsg);
    } finally {
      setLoadingUsers(false);
    }
  };

  const fetchUserStats = async () => {
    try {
      const response = await apiClient.users.getStats();
      if (response.success && response.data) {
        setUserStats(response.data);
      }
    } catch (error) {
      console.error("獲取使用者統計失敗:", error);
    }
  };

  const fetchScholarshipPermissions = async () => {
    setLoadingPermissions(true);

    try {
      const response = await apiClient.admin.getScholarshipPermissions();
      if (response.success && response.data) {
        setScholarshipPermissions(response.data);
      }
    } catch (error) {
      console.error("Error fetching permissions:", error);
    } finally {
      setLoadingPermissions(false);
    }
  };

  const fetchAvailableScholarships = async () => {
    try {
      const response = await apiClient.admin.getAllScholarshipsForPermissions();
      if (response.success && response.data) {
        setAvailableScholarships(response.data);
      }
    } catch (error) {
      console.error("獲取獎學金列表失敗:", error);
    }
  };

  const fetchAcademies = async () => {
    try {
      const response = await apiClient.referenceData.getAcademies();
      if (response.success && response.data) {
        setAcademies(response.data);
      }
    } catch (error) {
      console.error("獲取學院列表失敗:", error);
    }
  };

  useEffect(() => {
    if (user?.role === "super_admin") {
      fetchUsers();
      fetchUserStats();
      fetchScholarshipPermissions();
      fetchAvailableScholarships();
      fetchAcademies();
    }
  }, [user, userPagination.page]);

  useEffect(() => {
    if (user?.role === "super_admin") {
      fetchUsers();
    }
  }, [userSearch, userRoleFilter]);

  const handleUserFormChange = (field: keyof UserCreateForm, value: any) => {
    setUserForm((prev) => ({ ...prev, [field]: value }));

    if (field === "role") {
      if (!["college", "admin"].includes(value)) {
        if (editingUser) {
          setScholarshipPermissions((prev) =>
            prev.filter((p) => p.user_id !== Number(editingUser.id))
          );
        } else {
          setScholarshipPermissions((prev) => prev.filter((p) => p.user_id !== -1));
        }
      }
    }
  };

  const handleCreateUser = async () => {
    if (!userForm.nycu_id || !userForm.role) return;

    setUserFormLoading(true);

    try {
      // Only send fields that have values - SSO will populate the rest on first login
      const createData: any = {
        nycu_id: userForm.nycu_id,
        role: userForm.role,
      };

      // Add optional fields only if they have non-empty values
      if (userForm.comment) createData.comment = userForm.comment;
      if (userForm.college_code) createData.college_code = userForm.college_code;

      const response = await apiClient.users.create(createData);

      if (response.success) {
        const newUserId = response.data?.id;
        if (
          newUserId &&
          ["college", "admin", "super_admin"].includes(userForm.role)
        ) {
          const tempPermissions = scholarshipPermissions.filter(
            (p) => p.user_id === -1
          );
          if (tempPermissions.length > 0) {
            // Use bulk API to assign permissions
            await fetch(`/api/v1/users/${newUserId}/scholarships/bulk`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${localStorage.getItem("auth_token")}`,
              },
              body: JSON.stringify({
                scholarship_ids: tempPermissions.map((p) => p.scholarship_id),
                operation: "set",
              }),
            });
          }
        }

        setScholarshipPermissions((prev) => prev.filter((p) => p.user_id !== -1));
        setShowUserForm(false);
        resetUserForm();
        await fetchUsers();
        await fetchUserStats();
        await fetchScholarshipPermissions();
      } else {
        alert("建立使用者權限失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "建立使用者權限失敗: " +
          (error instanceof Error ? error.message : "網絡錯誤")
      );
    } finally {
      setUserFormLoading(false);
    }
  };

  const handleUpdateUser = async () => {
    if (!editingUser || !userForm.role) return;

    setUserFormLoading(true);

    try {
      const response = await apiClient.users.update(editingUser.id, userForm);

      if (response.success) {
        if (["college", "admin", "super_admin"].includes(userForm.role)) {
          const permissionsToSave = scholarshipPermissions.filter(
            (p) => p.user_id === Number(editingUser.id)
          );

          // Use bulk API to update permissions
          await fetch(
            `/api/v1/users/${editingUser.id}/scholarships/bulk`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${localStorage.getItem("auth_token")}`,
              },
              body: JSON.stringify({
                scholarship_ids: permissionsToSave.map((p) => p.scholarship_id),
                operation: "set",
              }),
            }
          );
        } else {
          // Remove all permissions for non-college/admin roles
          await fetch(
            `/api/v1/users/${editingUser.id}/scholarships/bulk`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${localStorage.getItem("auth_token")}`,
              },
              body: JSON.stringify({
                scholarship_ids: [],
                operation: "set",
              }),
            }
          );
        }

        setEditingUser(null);
        setShowUserForm(false);
        resetUserForm();
        await fetchUsers();
        await fetchUserStats();
        await fetchScholarshipPermissions();
      } else {
        alert("更新使用者權限失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "更新使用者權限失敗: " +
          (error instanceof Error ? error.message : "網絡錯誤")
      );
    } finally {
      setUserFormLoading(false);
    }
  };

  const handleEditUser = (user: UserListResponse) => {
    setEditingUser(user);
    setUserForm({
      nycu_id: user.nycu_id,
      email: user.email,
      name: user.name,
      role: user.role as any,
      user_type: user.user_type as any,
      status: user.status as any,
      dept_code: user.dept_code || "",
      dept_name: user.dept_name || "",
      comment: user.comment || "",
      raw_data: {
        chinese_name: user.raw_data?.chinese_name || "",
        english_name: user.raw_data?.english_name || "",
      },
      username: user.username || "",
      full_name: user.full_name || "",
      chinese_name: user.chinese_name || "",
      english_name: user.english_name || "",
      student_no: user.student_no || "",
      college_code: user.college_code || "",
    });
    setShowUserForm(true);
  };

  const resetUserForm = () => {
    setShowUserForm(false);
    setEditingUser(null);
    setScholarshipPermissions((prev) => prev.filter((p) => p.user_id !== -1));
    setUserForm({
      nycu_id: "",
      email: "",
      name: "",
      role: "college",
      user_type: "student",
      status: "在學",
      dept_code: "",
      dept_name: "",
      comment: "",
      raw_data: {
        chinese_name: "",
        english_name: "",
      },
      username: "",
      full_name: "",
      chinese_name: "",
      english_name: "",
      student_no: "",
    });
  };

  const getRoleLabel = (role: string) => {
    const roleMap: Record<string, string> = {
      student: "學生",
      professor: "教授",
      college: "學院",
      admin: "管理員",
      super_admin: "超級管理員",
    };
    return roleMap[role] || role;
  };

  const handleSearch = () => {
    setUserPagination((prev) => ({ ...prev, page: 1 }));
  };

  const clearFilters = () => {
    setUserSearch("");
    setUserRoleFilter("");
    setUserPagination((prev) => ({ ...prev, page: 1 }));
  };

  const handleUserSubmit = () => {
    if (editingUser) {
      handleUpdateUser();
    } else {
      handleCreateUser();
    }
  };

  const handlePermissionChange = useCallback(
    (permissions: any[]) => {
      const userId = editingUser?.id;
      if (userId) {
        const otherUserPermissions = scholarshipPermissions.filter(
          (p) => p.user_id !== Number(userId)
        );

        const newPermissions = permissions.map((permission) => {
          const scholarship = availableScholarships.find(
            (s) => s.id === permission.scholarship_id
          );

          const existingPermission = scholarshipPermissions.find(
            (p) =>
              p.user_id === Number(userId) &&
              p.scholarship_id === permission.scholarship_id
          );

          return {
            ...permission,
            id: existingPermission ? existingPermission.id : permission.id,
            user_id: Number(userId),
            scholarship_name: scholarship?.name || "未知獎學金",
            scholarship_name_en: scholarship?.name_en,
          };
        });

        const updatedPermissions = [...otherUserPermissions, ...newPermissions];
        setScholarshipPermissions(updatedPermissions);
      }
    },
    [editingUser, scholarshipPermissions, availableScholarships]
  );

  if (user?.role !== "super_admin") {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-gray-500">僅超級管理員可存取此功能</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">使用者權限管理</h3>
        <div className="flex gap-2">
          <Button
            onClick={() => setShowUserForm(true)}
            className="nycu-gradient text-white"
          >
            <Plus className="h-4 w-4 mr-1" />
            新增使用者權限
          </Button>
          <Button variant="outline">
            <Upload className="h-4 w-4 mr-1" />
            批次匯入
          </Button>
        </div>
      </div>

      {/* 使用者統計卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">總使用者數</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {userStats.total_users || 0}
            </div>
            <p className="text-xs text-muted-foreground">系統註冊用戶</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">在職使用者</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {userStats.status_distribution?.['在職'] || 0}
            </div>
            <p className="text-xs text-muted-foreground">目前在職狀態</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">學生用戶</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {userStats.role_distribution?.student || 0}
            </div>
            <p className="text-xs text-muted-foreground">學生角色</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">本月新增</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {userStats.recent_registrations || 0}
            </div>
            <p className="text-xs text-muted-foreground">最近30天</p>
          </CardContent>
        </Card>
      </div>

      {/* 搜尋和篩選 */}
      <Card className="border-nycu-blue-200">
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label>搜尋使用者</Label>
              <Input
                placeholder="姓名、信箱或 NYCU ID"
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                className="border-nycu-blue-200"
              />
            </div>
            <div>
              <Label>角色篩選</Label>
              <select
                value={userRoleFilter}
                onChange={(e) => setUserRoleFilter(e.target.value)}
                className="w-full px-3 py-2 border border-nycu-blue-200 rounded-md"
              >
                <option value="">全部管理角色</option>
                <option value="super_admin">超級管理員</option>
                <option value="admin">管理員</option>
                <option value="college">學院</option>
                <option value="professor">教授</option>
              </select>
            </div>
            <div className="flex items-end gap-2">
              <Button
                onClick={handleSearch}
                className="flex-1 nycu-gradient text-white"
              >
                搜尋
              </Button>
              <Button
                onClick={clearFilters}
                variant="outline"
                className="border-nycu-blue-300 text-nycu-blue-600 hover:bg-nycu-blue-50"
              >
                清除
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 使用者列表 */}
      <Card className="border-nycu-blue-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            使用者權限列表
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loadingUsers ? (
            <div className="flex items-center justify-center py-8">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                <span className="text-nycu-navy-600">載入使用者中...</span>
              </div>
            </div>
          ) : usersError ? (
            <div className="text-center py-12">
              <AlertCircle className="h-16 w-16 mx-auto mb-4 text-red-400" />
              <p className="text-lg font-medium text-red-600 mb-2">
                載入使用者失敗
              </p>
              <p className="text-sm text-gray-600 mb-4">{usersError}</p>
              <Button
                onClick={fetchUsers}
                variant="outline"
                className="border-red-300 text-red-600 hover:bg-red-50"
              >
                重試
              </Button>
            </div>
          ) : users.length > 0 ? (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-bold px-5 py-3">
                      使用者資訊
                    </TableHead>
                    <TableHead className="font-bold px-5 py-3">角色</TableHead>
                    <TableHead className="font-bold px-5 py-3 w-40">
                      單位
                    </TableHead>
                    <TableHead className="font-bold px-5 py-3">
                      獎學金管理權限
                    </TableHead>
                    <TableHead className="font-bold px-5 py-3">
                      註冊時間
                    </TableHead>
                    <TableHead className="font-bold px-5 py-3">
                      最後登入
                    </TableHead>
                    <TableHead className="font-bold px-5 py-3">
                      權限操作
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((user) => {
                    const userPermissions = scholarshipPermissions.filter(
                      (p) => p.user_id === Number(user.id)
                    );
                    return (
                      <TableRow key={user.id}>
                        <TableCell className="px-5 py-4 align-middle">
                          <div className="space-y-1">
                            <div className="font-medium whitespace-nowrap">{user.name}<span className="text-sm text-gray-500"> | {user.nycu_id}</span></div>
                            <div className="text-sm text-gray-500">
                              {user.email}
                            </div>
                            {user.raw_data?.chinese_name && (
                              <div className="text-sm text-gray-500">
                                中文名: {user.raw_data.chinese_name}
                              </div>
                            )}
                            {user.raw_data?.english_name && (
                              <div className="text-sm text-gray-500">
                                英文名: {user.raw_data.english_name}
                              </div>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="px-5 py-4 align-middle">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge
                              variant={
                                user.role === "super_admin"
                                  ? "destructive"
                                  : user.role === "admin"
                                    ? "default"
                                    : user.role === "college"
                                      ? "secondary"
                                      : user.role === "professor"
                                        ? "outline"
                                        : "default"
                              }
                              className="text-xs px-3 py-1 rounded-full whitespace-nowrap"
                            >
                              {getRoleLabel(user.role)}
                            </Badge>
                            {user.role === "college" && user.college_code && (
                              <Badge
                                variant="outline"
                                className="text-xs px-2 py-1 rounded-full whitespace-nowrap border-indigo-300 text-indigo-700 bg-indigo-50"
                              >
                                {academies.find(a => a.code === user.college_code)?.name || user.college_code}
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="px-5 py-4 align-middle w-40">
                          <div className="space-y-2">
                            {/* Portal 同步的單位資訊 (唯讀) */}
                            {user.dept_name ? (
                              <>
                                <div className="text-sm font-medium text-gray-900 truncate">
                                  {user.dept_name}
                                </div>
                                {user.dept_code && (
                                  <div className="text-xs text-gray-500">
                                    代碼: {user.dept_code}
                                  </div>
                                )}
                              </>
                            ) : (
                              <div className="text-sm text-gray-400">
                                未設定單位
                              </div>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="px-5 py-4 align-middle">
                          <div className="flex flex-wrap gap-2 min-h-[32px]">
                            {loadingPermissions ? (
                              <div className="text-xs text-gray-400">
                                載入中...
                              </div>
                            ) : user.role === "super_admin" ? (
                              <>
                                {availableScholarships.map((scholarship) => (
                                  <Badge
                                    key={scholarship.id}
                                    variant="default"
                                    className="text-xs px-3 py-1 rounded-full mb-1"
                                  >
                                    {scholarship.name}
                                  </Badge>
                                ))}
                                <div className="text-xs text-green-600 font-medium w-full">
                                  擁有所有獎學金權限
                                </div>
                              </>
                            ) : user.role === "professor" ? (
                              <div className="text-xs text-amber-600 font-medium">
                                教授無需管理權限
                              </div>
                            ) : userPermissions.length === 0 ? (
                              <div className="text-xs text-gray-400">
                                無獎學金權限
                              </div>
                            ) : (
                              userPermissions.map((permission) => (
                                <Badge
                                  key={permission.id}
                                  variant="secondary"
                                  className="text-xs px-3 py-1 rounded-full mb-1"
                                >
                                  {permission.scholarship_name}
                                </Badge>
                              ))
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="px-5 py-4 align-middle">
                          <div className="text-sm text-gray-600">
                            {new Date(user.created_at).toLocaleDateString(
                              "zh-TW",
                              {
                                year: "numeric",
                                month: "2-digit",
                                day: "2-digit",
                              }
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="px-5 py-4 align-middle">
                          <div className="text-sm text-gray-600">
                            {user.last_login_at
                              ? new Date(user.last_login_at).toLocaleString(
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
                                )
                              : "從未登入"}
                          </div>
                        </TableCell>
                        <TableCell className="px-5 py-4 align-middle">
                          <div className="flex gap-1">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleEditUser(user)}
                              className="hover:bg-nycu-blue-50 hover:border-nycu-blue-300"
                            >
                              <Edit className="h-4 w-4" />
                              {user.role === "professor"
                                ? "更改角色"
                                : "編輯權限"}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>

              {/* 分頁 */}
              <div className="flex items-center justify-between p-4 border-t">
                <div className="text-sm text-gray-600">
                  顯示 {(userPagination.page - 1) * userPagination.size + 1} 到{" "}
                  {Math.min(
                    userPagination.page * userPagination.size,
                    userPagination.total
                  )}{" "}
                  筆，共 {userPagination.total} 筆
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setUserPagination((prev) => ({
                        ...prev,
                        page: prev.page - 1,
                      }))
                    }
                    disabled={userPagination.page <= 1}
                  >
                    上一頁
                  </Button>
                  <span className="flex items-center px-3 text-sm">
                    第 {userPagination.page} 頁
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setUserPagination((prev) => ({
                        ...prev,
                        page: prev.page + 1,
                      }))
                    }
                    disabled={
                      userPagination.page * userPagination.size >=
                      userPagination.total
                    }
                  >
                    下一頁
                  </Button>
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-12 text-gray-500">
              <Users className="h-16 w-16 mx-auto mb-4 text-gray-300" />
              <p className="text-lg font-medium">尚無使用者權限資料</p>
              <p className="text-sm mt-2 mb-4">
                點擊「新增使用者權限」開始設定使用者權限
              </p>
              <Button onClick={fetchUsers} variant="outline" size="sm">
                重新載入
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 使用者編輯 Modal */}
      <UserEditModal
        isOpen={showUserForm}
        onClose={() => setShowUserForm(false)}
        editingUser={editingUser}
        userForm={userForm}
        onUserFormChange={handleUserFormChange}
        onSubmit={handleUserSubmit}
        isLoading={userFormLoading}
        scholarshipPermissions={scholarshipPermissions}
        availableScholarships={availableScholarships}
        onPermissionChange={handlePermissionChange}
      />
    </>
  );
}
