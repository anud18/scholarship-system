"use client";

import { useState, useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Upload,
  Download,
  FileSpreadsheet,
  Plus,
  Trash2,
  Search,
  AlertCircle,
  Loader2
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import apiClient, {
  ScholarshipConfiguration,
  WhitelistStudentInfo,
  WhitelistResponse
} from "@/lib/api";

interface WhitelistManagementDialogProps {
  isOpen: boolean;
  onClose: () => void;
  configuration: ScholarshipConfiguration;
  subTypes: string[];
}

export function WhitelistManagementDialog({
  isOpen,
  onClose,
  configuration,
  subTypes,
}: WhitelistManagementDialogProps) {
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // State
  const [whitelist, setWhitelist] = useState<WhitelistResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTab, setSelectedTab] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Add student form
  const [newStudentNycuId, setNewStudentNycuId] = useState("");
  const [newStudentSubType, setNewStudentSubType] = useState(subTypes[0] || "");
  const [addingStudent, setAddingStudent] = useState(false);

  // Selected students for batch delete (使用 nycu_id 作為鍵)
  const [selectedStudents, setSelectedStudents] = useState<Set<string>>(new Set());

  // Update newStudentSubType when subTypes changes
  useEffect(() => {
    if (subTypes.length > 0) {
      setNewStudentSubType(subTypes[0]);
    }
  }, [subTypes]);

  // Load whitelist
  useEffect(() => {
    if (isOpen) {
      loadWhitelist();
      setSelectedTab("all");
      setSearchQuery("");
      setSelectedStudents(new Set());
    }
  }, [isOpen, configuration.id]);

  const loadWhitelist = async () => {
    setLoading(true);
    try {
      const response = await apiClient.whitelist.getConfigurationWhitelist(configuration.id);
      if (response.success && response.data) {
        setWhitelist(response.data);
      }
    } catch (error: any) {
      toast({
        title: "載入失敗",
        description: error.message || "無法載入申請白名單",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  // Add student
  const handleAddStudent = async () => {
    if (!newStudentNycuId.trim() || !newStudentSubType) {
      toast({
        title: "輸入錯誤",
        description: "請填寫學號和選擇子獎學金類型",
        variant: "destructive",
      });
      return;
    }

    setAddingStudent(true);
    try {
      const response = await apiClient.whitelist.batchAddWhitelist(configuration.id, {
        students: [{ nycu_id: newStudentNycuId.trim(), sub_type: newStudentSubType }],
      });

      if (response.success) {
        toast({
          title: "新增成功",
          description: `已將學號 ${newStudentNycuId} 加入申請白名單`,
        });
        setNewStudentNycuId("");
        await loadWhitelist();
      } else if (response.data?.errors && response.data.errors.length > 0) {
        toast({
          title: "新增失敗",
          description: response.data.errors[0],
          variant: "destructive",
        });
      }
    } catch (error: any) {
      toast({
        title: "新增失敗",
        description: error.message || "無法新增學生到申請白名單",
        variant: "destructive",
      });
    } finally {
      setAddingStudent(false);
    }
  };

  // Delete students
  const handleDeleteStudents = async (nycuIds: string[], subType?: string) => {
    if (nycuIds.length === 0) return;

    try {
      const response = await apiClient.whitelist.batchRemoveWhitelist(configuration.id, {
        nycu_ids: nycuIds,
        sub_type: subType,
      });

      if (response.success) {
        toast({
          title: "刪除成功",
          description: `已移除 ${nycuIds.length} 位學生`,
        });
        setSelectedStudents(new Set());
        await loadWhitelist();
      }
    } catch (error: any) {
      toast({
        title: "刪除失敗",
        description: error.message || "無法刪除學生",
        variant: "destructive",
      });
    }
  };

  // Excel import
  const handleImportExcel = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setLoading(true);
    try {
      const response = await apiClient.whitelist.importWhitelistExcel(configuration.id, file);

      if (response.success && response.data) {
        const result = response.data;
        toast({
          title: "匯入完成",
          description: `成功: ${result.success_count} 筆，失敗: ${result.error_count} 筆`,
          variant: result.error_count > 0 ? "destructive" : "default",
        });

        if (result.errors.length > 0) {
          console.error("Import errors:", result.errors);
        }

        await loadWhitelist();
      }
    } catch (error: any) {
      toast({
        title: "匯入失敗",
        description: error.message || "無法匯入 Excel 檔案",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  // Excel export
  const handleExportExcel = async () => {
    try {
      const blob = await apiClient.whitelist.exportWhitelistExcel(configuration.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${configuration.scholarship_type_name}_申請白名單_${configuration.academic_year}_${configuration.semester || "annual"}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);

      toast({
        title: "匯出成功",
        description: "申請白名單已下載為 Excel 檔案",
      });
    } catch (error: any) {
      toast({
        title: "匯出失敗",
        description: error.message || "無法匯出申請白名單",
        variant: "destructive",
      });
    }
  };

  // Download template
  const handleDownloadTemplate = async () => {
    try {
      const blob = await apiClient.whitelist.downloadTemplate(configuration.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `申請白名單匯入模板_${configuration.scholarship_type_name}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);

      toast({
        title: "下載成功",
        description: "匯入模板已下載",
      });
    } catch (error: any) {
      toast({
        title: "下載失敗",
        description: error.message || "無法下載模板",
        variant: "destructive",
      });
    }
  };

  // Filter students
  const filteredWhitelist = whitelist.map(item => ({
    ...item,
    students: item.students.filter(
      student =>
        (selectedTab === "all" || item.sub_type === selectedTab) &&
        (searchQuery === "" ||
          student.nycu_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (student.name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false))
    ),
  })).filter(item => item.students.length > 0);

  const allStudents = whitelist.flatMap(item => item.students);
  const totalCount = allStudents.length;

  return (
    <>
      <Dialog open={isOpen} onOpenChange={onClose}>
        <DialogContent className="max-w-5xl max-h-[90vh]">
          <DialogHeader>
            <DialogTitle>申請白名單管理</DialogTitle>
            <DialogDescription>
              {configuration.scholarship_type_name} - {configuration.academic_year}學年度
              {configuration.semester ? ` ${configuration.semester === "first" ? "第一學期" : "第二學期"}` : ""}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Action Buttons */}
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={handleDownloadTemplate}>
                <FileSpreadsheet className="h-4 w-4 mr-1" />
                下載模板
              </Button>
              <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()}>
                <Upload className="h-4 w-4 mr-1" />
                匯入 Excel
              </Button>
              <Button size="sm" variant="outline" onClick={handleExportExcel}>
                <Download className="h-4 w-4 mr-1" />
                匯出 Excel
              </Button>
              <div className="flex-1" />
              <Badge variant="secondary">總計: {totalCount} 人</Badge>
            </div>

            <Separator />

            {/* Add Student Form */}
            <div className="border rounded-lg p-4 bg-muted/30">
              <h4 className="text-sm font-medium mb-3">新增學生</h4>
              <div className="flex gap-2">
                <div className="flex-1">
                  <Input
                    placeholder="請輸入學號"
                    value={newStudentNycuId}
                    onChange={e => setNewStudentNycuId(e.target.value)}
                    onKeyPress={e => e.key === "Enter" && handleAddStudent()}
                  />
                </div>
                <Select value={newStudentSubType} onValueChange={setNewStudentSubType}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {subTypes.map(type => (
                      <SelectItem key={type} value={type}>
                        {type}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button onClick={handleAddStudent} disabled={addingStudent}>
                  {addingStudent ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}
                  新增
                </Button>
              </div>
            </div>

            {/* Search and Filter */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="搜尋學號或姓名..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
              {selectedStudents.size > 0 && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleDeleteStudents(Array.from(selectedStudents))}
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  刪除選中 ({selectedStudents.size})
                </Button>
              )}
            </div>

            {/* Tabs by Sub-Type */}
            <Tabs value={selectedTab} onValueChange={setSelectedTab}>
              <TabsList>
                <TabsTrigger value="all">全部</TabsTrigger>
                {whitelist.map(item => (
                  <TabsTrigger key={item.sub_type} value={item.sub_type}>
                    {item.sub_type} ({item.total})
                  </TabsTrigger>
                ))}
              </TabsList>

              {/* Student Table */}
              <ScrollArea className="h-[400px] border rounded-md mt-4">
                {loading ? (
                  <div className="flex items-center justify-center h-full">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : filteredWhitelist.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                    <AlertCircle className="h-12 w-12 mb-2" />
                    <p>目前沒有申請白名單學生</p>
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-12">
                          <input
                            type="checkbox"
                            onChange={e => {
                              if (e.target.checked) {
                                const allNycuIds = new Set(filteredWhitelist.flatMap(item => item.students.map(s => s.nycu_id)));
                                setSelectedStudents(allNycuIds);
                              } else {
                                setSelectedStudents(new Set());
                              }
                            }}
                          />
                        </TableHead>
                        <TableHead>學號</TableHead>
                        <TableHead>姓名</TableHead>
                        <TableHead>子獎學金類型</TableHead>
                        <TableHead className="text-right">操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredWhitelist.flatMap(item =>
                        item.students.map(student => (
                          <TableRow key={student.nycu_id}>
                            <TableCell>
                              <input
                                type="checkbox"
                                checked={selectedStudents.has(student.nycu_id)}
                                onChange={e => {
                                  const newSet = new Set(selectedStudents);
                                  if (e.target.checked) {
                                    newSet.add(student.nycu_id);
                                  } else {
                                    newSet.delete(student.nycu_id);
                                  }
                                  setSelectedStudents(newSet);
                                }}
                              />
                            </TableCell>
                            <TableCell className="font-mono">{student.nycu_id}</TableCell>
                            <TableCell>
                              {student.is_registered ? (
                                <span>{student.name}</span>
                              ) : (
                                <span className="text-muted-foreground">
                                  學號：{student.nycu_id} <Badge variant="outline">未註冊</Badge>
                                </span>
                              )}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">{student.sub_type}</Badge>
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteStudents([student.nycu_id], student.sub_type)}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                )}
              </ScrollArea>
            </Tabs>
          </div>
        </DialogContent>
      </Dialog>

      {/* Hidden file input for Excel import */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xls"
        className="hidden"
        onChange={handleImportExcel}
      />
    </>
  );
}
