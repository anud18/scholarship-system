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
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
import { toast } from "@/hooks/use-toast";
import {
  api,
  ProfessorStudentRelationship,
  ProfessorStudentRelationshipCreate,
  ProfessorStudentRelationshipUpdate,
} from "@/lib/api";
import {
  RelationshipType,
  RelationshipStatus,
  getRelationshipTypeLabel,
  getRelationshipStatusLabel,
} from "@/lib/enums";
import {
  Users,
  UserPlus,
  Edit,
  Trash2,
  Search,
  Filter,
  GraduationCap,
  User,
  Calendar,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Plus,
  Save,
  X,
} from "lucide-react";

// Using API types directly

export default function ProfessorStudentRelationshipManagement() {
  const [relationships, setRelationships] = useState<
    ProfessorStudentRelationship[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [relationshipTypeFilter, setRelationshipTypeFilter] =
    useState<string>("all");
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [editingRelationship, setEditingRelationship] =
    useState<ProfessorStudentRelationship | null>(null);

  const [newRelationship, setNewRelationship] =
    useState<ProfessorStudentRelationshipCreate>({
      professor_id: 0,
      student_id: 0,
      relationship_type: "advisor",
      status: "active",
      start_date: new Date().toISOString().split("T")[0],
      notes: "",
    });

  const relationshipTypes = [
    { value: "advisor", label: "指導教授", description: "主要指導教授" },
    { value: "supervisor", label: "監督教授", description: "研究監督教授" },
    {
      value: "committee_member",
      label: "委員會成員",
      description: "論文委員會成員",
    },
    { value: "co_advisor", label: "共同指導", description: "共同指導教授" },
  ];

  const statusOptions = [
    {
      value: "active",
      label: "活躍",
      color: "bg-green-100 text-green-800",
      description: "關係正在進行中",
    },
    {
      value: "inactive",
      label: "非活躍",
      color: "bg-gray-100 text-gray-800",
      description: "暫時停止的關係",
    },
    {
      value: "pending",
      label: "待確認",
      color: "bg-yellow-100 text-yellow-800",
      description: "等待確認的關係",
    },
    {
      value: "terminated",
      label: "已終止",
      color: "bg-red-100 text-red-800",
      description: "已結束的關係",
    },
  ];

  useEffect(() => {
    loadRelationships();
  }, []);

  const loadRelationships = async () => {
    try {
      setLoading(true);
      const response =
        await api.professorStudent.getProfessorStudentRelationships();
      if (response.success && response.data) {
        setRelationships(response.data);
      }
    } catch (error) {
      toast({
        title: "載入失敗",
        description: "無法載入教授學生關係資料",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRelationship = async () => {
    try {
      const response =
        await api.professorStudent.createProfessorStudentRelationship(
          newRelationship
        );
      if (response.success) {
        toast({
          title: "建立成功",
          description: "教授學生關係已成功建立",
        });
        setShowCreateDialog(false);
        setNewRelationship({
          professor_id: 0,
          student_id: 0,
          relationship_type: "advisor",
          status: "active",
          start_date: new Date().toISOString().split("T")[0],
          notes: "",
        });
        loadRelationships();
      }
    } catch (error) {
      toast({
        title: "建立失敗",
        description: "無法建立教授學生關係",
        variant: "destructive",
      });
    }
  };

  const handleUpdateRelationship = async (
    relationship: ProfessorStudentRelationship
  ) => {
    try {
      const updateData: ProfessorStudentRelationshipUpdate = {
        id: relationship.id,
        professor_id: relationship.professor_id,
        student_id: relationship.student_id,
        relationship_type: relationship.relationship_type,
        status: relationship.status,
        start_date: relationship.start_date,
        end_date: relationship.end_date,
        notes: relationship.notes,
      };

      const response =
        await api.professorStudent.updateProfessorStudentRelationship(
          relationship.id,
          updateData
        );
      if (response.success) {
        toast({
          title: "更新成功",
          description: "教授學生關係已成功更新",
        });
        setEditingRelationship(null);
        loadRelationships();
      }
    } catch (error) {
      toast({
        title: "更新失敗",
        description: "無法更新教授學生關係",
        variant: "destructive",
      });
    }
  };

  const handleDeleteRelationship = async (id: number) => {
    if (!confirm("確定要刪除這個教授學生關係嗎？此操作無法復原。")) {
      return;
    }

    try {
      const response =
        await api.professorStudent.deleteProfessorStudentRelationship(id);
      if (response.success) {
        toast({
          title: "刪除成功",
          description: "教授學生關係已成功刪除",
        });
        loadRelationships();
      }
    } catch (error) {
      toast({
        title: "刪除失敗",
        description: "無法刪除教授學生關係",
        variant: "destructive",
      });
    }
  };

  const getStatusBadge = (status: string) => {
    const statusConfig = statusOptions.find(option => option.value === status);
    return (
      <Badge className={statusConfig?.color || "bg-gray-100 text-gray-800"}>
        {statusConfig?.label || status}
      </Badge>
    );
  };

  const getRelationshipTypeDisplayLabel = (type: string) => {
    const typeConfig = relationshipTypes.find(t => t.value === type);
    return typeConfig?.label || type;
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "active":
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case "inactive":
        return <XCircle className="h-4 w-4 text-gray-600" />;
      case "pending":
        return <AlertTriangle className="h-4 w-4 text-yellow-600" />;
      case "terminated":
        return <XCircle className="h-4 w-4 text-red-600" />;
      default:
        return <AlertTriangle className="h-4 w-4 text-gray-600" />;
    }
  };

  const filteredRelationships = relationships.filter(relationship => {
    const matchesSearch =
      searchTerm === "" ||
      relationship.professor?.name
        .toLowerCase()
        .includes(searchTerm.toLowerCase()) ||
      relationship.student?.name
        .toLowerCase()
        .includes(searchTerm.toLowerCase()) ||
      relationship.professor?.nycu_id
        ?.toLowerCase()
        .includes(searchTerm.toLowerCase()) ||
      relationship.student?.student_no
        ?.toLowerCase()
        .includes(searchTerm.toLowerCase());

    const matchesStatus =
      statusFilter === "all" || relationship.status === statusFilter;
    const matchesType =
      relationshipTypeFilter === "all" ||
      relationship.relationship_type === relationshipTypeFilter;

    return matchesSearch && matchesStatus && matchesType;
  });

  const getStatistics = () => {
    const total = relationships.length;
    const active = relationships.filter(r => r.status === "active").length;
    const pending = relationships.filter(r => r.status === "pending").length;
    const terminated = relationships.filter(
      r => r.status === "terminated"
    ).length;

    return { total, active, pending, terminated };
  };

  const stats = getStatistics();

  if (loading) {
    return <div className="p-6">載入中...</div>;
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">教授學生關係管理</h1>
          <p className="text-muted-foreground">管理教授與學生之間的指導關係</p>
        </div>
        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              新增關係
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>建立新的教授學生關係</DialogTitle>
              <DialogDescription>
                設定教授與學生之間的指導關係
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="professor_id">教授 ID</Label>
                  <Input
                    id="professor_id"
                    type="number"
                    value={newRelationship.professor_id || ""}
                    onChange={e =>
                      setNewRelationship(prev => ({
                        ...prev,
                        professor_id: parseInt(e.target.value) || 0,
                      }))
                    }
                    placeholder="輸入教授 ID"
                  />
                </div>
                <div>
                  <Label htmlFor="student_id">學生 ID</Label>
                  <Input
                    id="student_id"
                    type="number"
                    value={newRelationship.student_id || ""}
                    onChange={e =>
                      setNewRelationship(prev => ({
                        ...prev,
                        student_id: parseInt(e.target.value) || 0,
                      }))
                    }
                    placeholder="輸入學生 ID"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="relationship_type">關係類型</Label>
                  <Select
                    value={newRelationship.relationship_type}
                    onValueChange={(value: any) =>
                      setNewRelationship(prev => ({
                        ...prev,
                        relationship_type: value,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {relationshipTypes.map(type => (
                        <SelectItem key={type.value} value={type.value}>
                          <div>
                            <div className="font-medium">{type.label}</div>
                            <div className="text-sm text-muted-foreground">
                              {type.description}
                            </div>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="status">狀態</Label>
                  <Select
                    value={newRelationship.status}
                    onValueChange={(value: any) =>
                      setNewRelationship(prev => ({
                        ...prev,
                        status: value,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {statusOptions.map(status => (
                        <SelectItem key={status.value} value={status.value}>
                          <div>
                            <div className="font-medium">{status.label}</div>
                            <div className="text-sm text-muted-foreground">
                              {status.description}
                            </div>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="start_date">開始日期</Label>
                  <Input
                    id="start_date"
                    type="date"
                    value={newRelationship.start_date}
                    onChange={e =>
                      setNewRelationship(prev => ({
                        ...prev,
                        start_date: e.target.value,
                      }))
                    }
                  />
                </div>
                <div>
                  <Label htmlFor="end_date">結束日期（可選）</Label>
                  <Input
                    id="end_date"
                    type="date"
                    value={newRelationship.end_date || ""}
                    onChange={e =>
                      setNewRelationship(prev => ({
                        ...prev,
                        end_date: e.target.value || undefined,
                      }))
                    }
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="notes">備註</Label>
                <Input
                  id="notes"
                  value={newRelationship.notes || ""}
                  onChange={e =>
                    setNewRelationship(prev => ({
                      ...prev,
                      notes: e.target.value,
                    }))
                  }
                  placeholder="關係備註資訊"
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setShowCreateDialog(false)}
              >
                取消
              </Button>
              <Button onClick={handleCreateRelationship}>建立關係</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Statistics Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">總關係數</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
            <p className="text-xs text-muted-foreground">全部教授學生關係</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">活躍關係</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.active}</div>
            <p className="text-xs text-muted-foreground">正在進行的關係</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">待確認</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.pending}</div>
            <p className="text-xs text-muted-foreground">等待確認的關係</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">已終止</CardTitle>
            <XCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.terminated}</div>
            <p className="text-xs text-muted-foreground">已結束的關係</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle>篩選條件</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <div className="flex-1">
              <Label>搜尋</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  placeholder="搜尋教授或學生姓名、ID"
                  value={searchTerm}
                  onChange={e => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <div>
              <Label>狀態篩選</Label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-48">
                  <SelectValue placeholder="選擇狀態" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部狀態</SelectItem>
                  {statusOptions.map(status => (
                    <SelectItem key={status.value} value={status.value}>
                      {status.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>關係類型</Label>
              <Select
                value={relationshipTypeFilter}
                onValueChange={setRelationshipTypeFilter}
              >
                <SelectTrigger className="w-48">
                  <SelectValue placeholder="選擇類型" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部類型</SelectItem>
                  {relationshipTypes.map(type => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button variant="outline" onClick={loadRelationships}>
                <RefreshCw className="h-4 w-4 mr-2" />
                重新載入
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Relationships Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            教授學生關係列表
          </CardTitle>
          <CardDescription>
            共 {filteredRelationships.length} 個關係
          </CardDescription>
        </CardHeader>
        <CardContent>
          {filteredRelationships.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>教授</TableHead>
                  <TableHead>學生</TableHead>
                  <TableHead>關係類型</TableHead>
                  <TableHead>狀態</TableHead>
                  <TableHead>開始日期</TableHead>
                  <TableHead>結束日期</TableHead>
                  <TableHead>備註</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRelationships.map(relationship => (
                  <TableRow key={relationship.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <User className="h-4 w-4" />
                        <div>
                          <div className="font-medium">
                            {relationship.professor?.name ||
                              `教授 #${relationship.professor_id}`}
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {relationship.professor?.nycu_id ||
                              relationship.professor?.email}
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <GraduationCap className="h-4 w-4" />
                        <div>
                          <div className="font-medium">
                            {relationship.student?.name ||
                              `學生 #${relationship.student_id}`}
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {relationship.student?.student_no ||
                              relationship.student?.email}
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {getRelationshipTypeDisplayLabel(
                          relationship.relationship_type
                        )}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {getStatusIcon(relationship.status)}
                        {getStatusBadge(relationship.status)}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Calendar className="h-4 w-4 text-muted-foreground" />
                        {new Date(relationship.start_date).toLocaleDateString(
                          "zh-TW"
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      {relationship.end_date ? (
                        <div className="flex items-center gap-1">
                          <Calendar className="h-4 w-4 text-muted-foreground" />
                          {new Date(relationship.end_date).toLocaleDateString(
                            "zh-TW"
                          )}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">進行中</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div
                        className="max-w-32 truncate"
                        title={relationship.notes}
                      >
                        {relationship.notes || "-"}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setEditingRelationship(relationship)}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            handleDeleteRelationship(relationship.id)
                          }
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <Users className="h-16 w-16 mx-auto mb-4 text-gray-300" />
              <p className="text-lg font-medium">尚無關係資料</p>
              <p className="text-sm mt-2">目前沒有符合條件的教授學生關係</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Edit Dialog */}
      {editingRelationship && (
        <Dialog
          open={!!editingRelationship}
          onOpenChange={() => setEditingRelationship(null)}
        >
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>編輯教授學生關係</DialogTitle>
              <DialogDescription>修改現有的教授學生關係資訊</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="edit-professor_id">教授 ID</Label>
                  <Input
                    id="edit-professor_id"
                    type="number"
                    value={editingRelationship.professor_id}
                    onChange={e =>
                      setEditingRelationship(prev =>
                        prev
                          ? {
                              ...prev,
                              professor_id: parseInt(e.target.value) || 0,
                            }
                          : null
                      )
                    }
                  />
                </div>
                <div>
                  <Label htmlFor="edit-student_id">學生 ID</Label>
                  <Input
                    id="edit-student_id"
                    type="number"
                    value={editingRelationship.student_id}
                    onChange={e =>
                      setEditingRelationship(prev =>
                        prev
                          ? {
                              ...prev,
                              student_id: parseInt(e.target.value) || 0,
                            }
                          : null
                      )
                    }
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="edit-relationship_type">關係類型</Label>
                  <Select
                    value={editingRelationship.relationship_type}
                    onValueChange={(value: any) =>
                      setEditingRelationship(prev =>
                        prev
                          ? {
                              ...prev,
                              relationship_type: value,
                            }
                          : null
                      )
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {relationshipTypes.map(type => (
                        <SelectItem key={type.value} value={type.value}>
                          {type.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="edit-status">狀態</Label>
                  <Select
                    value={editingRelationship.status}
                    onValueChange={(value: any) =>
                      setEditingRelationship(prev =>
                        prev
                          ? {
                              ...prev,
                              status: value,
                            }
                          : null
                      )
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {statusOptions.map(status => (
                        <SelectItem key={status.value} value={status.value}>
                          {status.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="edit-start_date">開始日期</Label>
                  <Input
                    id="edit-start_date"
                    type="date"
                    value={editingRelationship.start_date}
                    onChange={e =>
                      setEditingRelationship(prev =>
                        prev
                          ? {
                              ...prev,
                              start_date: e.target.value,
                            }
                          : null
                      )
                    }
                  />
                </div>
                <div>
                  <Label htmlFor="edit-end_date">結束日期</Label>
                  <Input
                    id="edit-end_date"
                    type="date"
                    value={editingRelationship.end_date || ""}
                    onChange={e =>
                      setEditingRelationship(prev =>
                        prev
                          ? {
                              ...prev,
                              end_date: e.target.value || undefined,
                            }
                          : null
                      )
                    }
                  />
                </div>
              </div>
              <div>
                <Label htmlFor="edit-notes">備註</Label>
                <Input
                  id="edit-notes"
                  value={editingRelationship.notes || ""}
                  onChange={e =>
                    setEditingRelationship(prev =>
                      prev
                        ? {
                            ...prev,
                            notes: e.target.value,
                          }
                        : null
                    )
                  }
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setEditingRelationship(null)}
              >
                <X className="h-4 w-4 mr-2" />
                取消
              </Button>
              <Button
                onClick={() =>
                  editingRelationship &&
                  handleUpdateRelationship(editingRelationship)
                }
              >
                <Save className="h-4 w-4 mr-2" />
                儲存
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
