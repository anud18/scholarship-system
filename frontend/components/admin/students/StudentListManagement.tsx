"use client";

import { useState, useEffect } from "react";
import { apiClient } from "@/lib/api";
import type { Student, StudentStats } from "@/lib/api";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { GraduationCap, Users, UserCheck, X, Search, Eye } from "lucide-react";
import { StudentDetailModal } from "./StudentDetailModal";

export function StudentListManagement() {
  const [students, setStudents] = useState<Student[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<StudentStats>({
    total_students: 0,
    status_distribution: {},
    dept_distribution: {},
    recent_registrations: 0,
  });

  const [pagination, setPagination] = useState({
    page: 1,
    size: 20,
    total: 0,
    pages: 0,
  });

  const [search, setSearch] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const [selectedStudent, setSelectedStudent] = useState<Student | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  // Fetch students
  const fetchStudents = async () => {
    setLoading(true);
    setError(null);

    try {
      const params: any = {
        page: pagination.page,
        size: pagination.size,
      };

      if (search) params.search = search;
      if (deptFilter) params.dept_code = deptFilter;
      if (statusFilter) params.status = statusFilter;

      // Use apiClient instead of direct fetch
      const response = await apiClient.students.getAll(params);

      if (response.success && response.data) {
        setStudents(response.data.items || []);
        setPagination({
          page: response.data.page,
          size: response.data.size,
          total: response.data.total,
          pages: response.data.pages,
        });
      } else {
        setError(response.message || "獲取學生列表失敗");
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "網絡錯誤";
      setError(errorMsg);
      console.error("Error fetching students:", err);
    } finally {
      setLoading(false);
    }
  };

  // Fetch statistics
  const fetchStats = async () => {
    try {
      // Use apiClient instead of direct fetch
      const response = await apiClient.students.getStats();

      if (response.success && response.data) {
        setStats(response.data);
      }
    } catch (error) {
      console.error("獲取學生統計失敗:", error);
    }
  };

  // Initial load
  useEffect(() => {
    fetchStudents();
    fetchStats();
  }, [pagination.page, pagination.size]);

  // Search and filter handler
  const handleSearch = () => {
    setPagination((prev) => ({ ...prev, page: 1 }));
    fetchStudents();
  };

  const handleClearFilters = () => {
    setSearch("");
    setDeptFilter("");
    setStatusFilter("");
    setPagination((prev) => ({ ...prev, page: 1 }));
    setTimeout(() => fetchStudents(), 0);
  };

  const handleViewDetails = (student: Student) => {
    setSelectedStudent(student);
    setShowDetailModal(true);
  };

  // Format date
  const formatDate = (dateString?: string) => {
    if (!dateString) return "未登入";
    return new Date(dateString).toLocaleString("zh-TW", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // Get status badge color
  const getStatusBadge = (status?: string) => {
    if (!status) return <Badge variant="outline">未知</Badge>;

    const statusMap: Record<string, { label: string; variant: "default" | "secondary" | "outline" }> = {
      "在學": { label: "在學", variant: "default" },
      "畢業": { label: "畢業", variant: "secondary" },
      "在職": { label: "在職", variant: "outline" },
      "退休": { label: "退休", variant: "outline" },
    };

    const config = statusMap[status] || { label: status, variant: "outline" };
    return <Badge variant={config.variant}>{config.label}</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Title */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">學生列表</h2>
          <p className="text-sm text-muted-foreground">
            查看和管理所有學生用戶資訊
          </p>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">總學生數</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_students}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">在學學生</CardTitle>
            <GraduationCap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats.status_distribution["在學"] || 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">畢業學生</CardTitle>
            <UserCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats.status_distribution["畢業"] || 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">本月新增</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.recent_registrations}</div>
          </CardContent>
        </Card>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1">
              <Label htmlFor="search">搜尋</Label>
              <Input
                id="search"
                placeholder="學號、姓名或信箱"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && handleSearch()}
              />
            </div>

            <div className="w-full md:w-48">
              <Label htmlFor="status">狀態篩選</Label>
              <Select value={statusFilter || undefined} onValueChange={setStatusFilter}>
                <SelectTrigger id="status">
                  <SelectValue placeholder="全部狀態" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="在學">在學</SelectItem>
                  <SelectItem value="畢業">畢業</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-end gap-2">
              <Button onClick={handleSearch}>
                <Search className="mr-2 h-4 w-4" />
                搜尋
              </Button>
              <Button variant="outline" onClick={handleClearFilters}>
                <X className="mr-2 h-4 w-4" />
                清除
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error Display */}
      {error && (
        <Card className="border-red-500">
          <CardContent className="pt-6">
            <p className="text-red-500">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Student List Table */}
      <Card>
        <CardHeader>
          <CardTitle>學生列表</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[120px]">學號</TableHead>
                  <TableHead className="w-[150px]">姓名</TableHead>
                  <TableHead className="w-[200px]">信箱</TableHead>
                  <TableHead className="w-[150px]">系所</TableHead>
                  <TableHead className="w-[80px]">狀態</TableHead>
                  <TableHead className="w-[120px]">註冊時間</TableHead>
                  <TableHead className="w-[120px]">最後登入</TableHead>
                  <TableHead className="w-[100px]">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8">
                      載入中...
                    </TableCell>
                  </TableRow>
                ) : students.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8">
                      沒有找到學生
                    </TableCell>
                  </TableRow>
                ) : (
                  students.map((student) => (
                    <TableRow key={student.id}>
                      <TableCell className="font-mono">
                        {student.nycu_id}
                      </TableCell>
                      <TableCell>{student.name}</TableCell>
                      <TableCell className="text-sm">{student.email}</TableCell>
                      <TableCell>{student.dept_name || "未設定"}</TableCell>
                      <TableCell>{getStatusBadge(student.status)}</TableCell>
                      <TableCell className="text-sm">
                        {formatDate(student.created_at)}
                      </TableCell>
                      <TableCell className="text-sm">
                        {formatDate(student.last_login_at)}
                      </TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleViewDetails(student)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4">
            <div className="text-sm text-muted-foreground">
              顯示第 {(pagination.page - 1) * pagination.size + 1}-
              {Math.min(pagination.page * pagination.size, pagination.total)} 筆，
              共 {pagination.total} 筆
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={pagination.page <= 1}
                onClick={() =>
                  setPagination((prev) => ({ ...prev, page: prev.page - 1 }))
                }
              >
                上一頁
              </Button>
              <div className="flex items-center px-3 text-sm">
                第 {pagination.page} / {pagination.pages} 頁
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={pagination.page >= pagination.pages}
                onClick={() =>
                  setPagination((prev) => ({ ...prev, page: prev.page + 1 }))
                }
              >
                下一頁
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Student Detail Modal */}
      {selectedStudent && (
        <StudentDetailModal
          student={selectedStudent}
          open={showDetailModal}
          onClose={() => {
            setShowDetailModal(false);
            setSelectedStudent(null);
          }}
        />
      )}
    </div>
  );
}
