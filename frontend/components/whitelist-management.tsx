"use client";

import { useState } from "react";
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
import { Badge } from "@/components/ui/badge";
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
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Upload, Download, Trash2, Edit, FileText } from "lucide-react";

interface WhitelistStudent {
  id: string;
  studentId: string;
  studentName: string;
  department: string;
  gpa: number;
  reason: string;
  addedAt: string;
  addedBy: string;
  scholarshipType?: string;
}

interface WhitelistManagementProps {
  scholarshipType?: string;
  title?: string;
}

export function WhitelistManagement({
  scholarshipType = "undergraduate_freshman",
  title = "白名單管理",
}: WhitelistManagementProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 白名單學生資料 (模擬資料) - 改為狀態變數
  const [whitelistStudents, setWhitelistStudents] = useState<
    WhitelistStudent[]
  >([
    {
      id: "wl_undergrad_001",
      studentId: "U1120001",
      studentName: "張小明",
      department: "資訊工程學系",
      gpa: 3.85,
      reason: "特殊才能表現優異",
      addedAt: "2025-06-01",
      addedBy: "系統管理員",
      scholarshipType: "undergraduate_freshman",
    },
    {
      id: "wl_undergrad_002",
      studentId: "U1120002",
      studentName: "李美玲",
      department: "電機工程學系",
      gpa: 3.92,
      reason: "國際競賽獲獎",
      addedAt: "2025-06-02",
      addedBy: "系統管理員",
      scholarshipType: "undergraduate_freshman",
    },
    {
      id: "wl_undergrad_003",
      studentId: "U1120003",
      studentName: "王建國",
      department: "電子工程學系",
      gpa: 3.78,
      reason: "學術表現優異",
      addedAt: "2025-06-03",
      addedBy: "系統管理員",
      scholarshipType: "undergraduate_freshman",
    },
  ]);

  const handleAddToWhitelist = async (studentId: string) => {
    try {
      setIsLoading(true);
      // TODO: 實現 API 調用
      // await api.admin.addToWhitelist({
      //   scholarshipType: "undergraduate_freshman",
      //   studentId
      // })
      console.log("學生已加入白名單:", studentId);
    } catch (error) {
      setError("加入白名單失敗");
    } finally {
      setIsLoading(false);
    }
  };

  const handleRemoveFromWhitelist = async (studentId: string) => {
    try {
      setIsLoading(true);
      // TODO: 實現 API 調用
      // await api.admin.removeFromWhitelist({
      //   scholarshipType: "undergraduate_freshman",
      //   studentId
      // })
      console.log("學生已從白名單移除:", studentId);
    } catch (error) {
      setError("移除白名單失敗");
    } finally {
      setIsLoading(false);
    }
  };

  const [newStudent, setNewStudent] = useState({
    studentId: "",
    studentName: "",
    department: "",
    gpa: "",
    reason: "",
  });

  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);

  const handleAddStudent = () => {
    const student: WhitelistStudent = {
      id: `wl_${scholarshipType}_${Date.now()}`,
      studentId: newStudent.studentId,
      studentName: newStudent.studentName,
      department: newStudent.department,
      gpa: Number.parseFloat(newStudent.gpa),
      reason: newStudent.reason,
      addedAt: new Date().toISOString().split("T")[0],
      addedBy: "系統管理員",
      scholarshipType: scholarshipType,
    };

    setWhitelistStudents(prev => [...prev, student]);
    setNewStudent({
      studentId: "",
      studentName: "",
      department: "",
      gpa: "",
      reason: "",
    });
    setIsAddDialogOpen(false);
  };

  const handleRemoveStudent = (id: string) => {
    setWhitelistStudents(prev => prev.filter(s => s.id !== id));
  };

  const handleBatchImport = () => {
    // 實現批次匯入功能
    console.log("批次匯入白名單");
  };

  const handleExportList = () => {
    // 實現匯出功能
    console.log("匯出白名單");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5" />
          {title}
        </CardTitle>
        <CardDescription>
          管理可申請獎學金的學生白名單 - 僅限白名單內的學生才能申請
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex gap-2">
            <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
              <DialogTrigger asChild>
                <Button>
                  <Plus className="h-4 w-4 mr-1" />
                  新增學生
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>新增白名單學生</DialogTitle>
                  <DialogDescription>
                    新增可申請獎學金的學生至白名單
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>學號 *</Label>
                      <Input
                        value={newStudent.studentId}
                        onChange={e =>
                          setNewStudent({
                            ...newStudent,
                            studentId: e.target.value,
                          })
                        }
                        placeholder="例: B10901001"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>姓名 *</Label>
                      <Input
                        value={newStudent.studentName}
                        onChange={e =>
                          setNewStudent({
                            ...newStudent,
                            studentName: e.target.value,
                          })
                        }
                        placeholder="學生姓名"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>系所 *</Label>
                      <Input
                        value={newStudent.department}
                        onChange={e =>
                          setNewStudent({
                            ...newStudent,
                            department: e.target.value,
                          })
                        }
                        placeholder="例: 資訊工程學系"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>GPA *</Label>
                      <Input
                        type="number"
                        step="0.01"
                        value={newStudent.gpa}
                        onChange={e =>
                          setNewStudent({ ...newStudent, gpa: e.target.value })
                        }
                        placeholder="例: 3.25"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label>核准原因 *</Label>
                    <Textarea
                      value={newStudent.reason}
                      onChange={e =>
                        setNewStudent({ ...newStudent, reason: e.target.value })
                      }
                      placeholder="請說明核准該學生申請獎學金的原因..."
                      rows={3}
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button
                      onClick={handleAddStudent}
                      disabled={
                        !newStudent.studentId ||
                        !newStudent.studentName ||
                        !newStudent.department ||
                        !newStudent.gpa ||
                        !newStudent.reason
                      }
                    >
                      新增
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setIsAddDialogOpen(false)}
                    >
                      取消
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>

            <Button variant="outline" onClick={handleBatchImport}>
              <Upload className="h-4 w-4 mr-1" />
              批次匯入
            </Button>
          </div>

          <Button variant="outline" onClick={handleExportList}>
            <Download className="h-4 w-4 mr-1" />
            匯出名單
          </Button>
        </div>

        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>學號</TableHead>
                <TableHead>姓名</TableHead>
                <TableHead>系所</TableHead>
                <TableHead>GPA</TableHead>
                <TableHead>核准原因</TableHead>
                <TableHead>新增日期</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {whitelistStudents.map(student => (
                <TableRow key={student.id}>
                  <TableCell className="font-medium">
                    {student.studentId}
                  </TableCell>
                  <TableCell>{student.studentName}</TableCell>
                  <TableCell>{student.department}</TableCell>
                  <TableCell>
                    <Badge variant="default">{student.gpa}</Badge>
                  </TableCell>
                  <TableCell className="max-w-xs">
                    <div className="truncate" title={student.reason}>
                      {student.reason}
                    </div>
                  </TableCell>
                  <TableCell>{student.addedAt}</TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="outline" size="sm">
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleRemoveStudent(student.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="text-sm text-muted-foreground">
          共 {whitelistStudents.length} 位學生在白名單中
        </div>
      </CardContent>
    </Card>
  );
}
