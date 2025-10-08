"use client";

import React, { useState, useCallback, useEffect } from "react";
import { apiClient } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Upload,
  FileSpreadsheet,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Download,
  Eye,
  History,
  X,
} from "lucide-react";

interface BatchImportPanelProps {
  locale?: "zh" | "en";
}

interface Scholarship {
  id: number;
  name: string;
  name_en?: string;
  code: string;
  category?: string;
  application_cycle?: string;
}

interface PeriodOption {
  value: string;
  academic_year: number;
  semester: string | null;
  label: string;
  label_en: string;
  is_current: boolean;
  cycle: string;
  sort_order: number;
}

interface UploadedBatch {
  batch_id: number;
  file_name: string;
  total_records: number;
  preview_data: Array<Record<string, any>>;
  validation_summary: {
    valid_count: number;
    invalid_count: number;
    warnings: any[];
    errors: Array<{
      row: number;
      field?: string;
      message: string;
    }>;
  };
}

interface ImportHistoryItem {
  id: string;
  file_name: string;
  uploaded_by: number;
  uploaded_at: string;
  total_records: number;
  success_count: number;
  failed_count: number;
  status: "pending" | "completed" | "failed";
  scholarship_type: string;
  academic_year: number;
  semester: string;
}

export function BatchImportPanel({ locale = "zh" }: BatchImportPanelProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [scholarships, setScholarships] = useState<Scholarship[]>([]);
  const [selectedScholarship, setSelectedScholarship] = useState<Scholarship | null>(null);
  const [periods, setPeriods] = useState<PeriodOption[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<string>("");
  const [cycle, setCycle] = useState<string>("semester");
  const [isUploading, setIsUploading] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [uploadedBatch, setUploadedBatch] = useState<UploadedBatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ImportHistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoadingScholarships, setIsLoadingScholarships] = useState(false);
  const [isLoadingPeriods, setIsLoadingPeriods] = useState(false);

  // Fetch scholarships on mount
  useEffect(() => {
    fetchScholarships();
    fetchHistory();
  }, []);

  // Fetch periods when scholarship is selected
  useEffect(() => {
    if (selectedScholarship) {
      fetchPeriods(selectedScholarship.code);
    } else {
      setPeriods([]);
      setSelectedPeriod("");
    }
  }, [selectedScholarship]);

  const fetchScholarships = async () => {
    setIsLoadingScholarships(true);
    try {
      const response = await apiClient.admin.getMyScholarships();
      if (response.success && response.data) {
        setScholarships(response.data);
      }
    } catch (error) {
      console.error("Failed to fetch scholarships:", error);
      setError(locale === "zh" ? "無法載入獎學金列表" : "Failed to load scholarships");
    } finally {
      setIsLoadingScholarships(false);
    }
  };

  const fetchPeriods = async (scholarshipCode: string) => {
    setIsLoadingPeriods(true);
    try {
      const response = await apiClient.referenceData.getScholarshipPeriods({
        scholarship_code: scholarshipCode,
      });
      if (response.success && response.data) {
        setPeriods(response.data.periods);
        setCycle(response.data.cycle);
        // Auto-select current period
        const currentPeriod = response.data.periods.find((p) => p.is_current);
        if (currentPeriod) {
          setSelectedPeriod(currentPeriod.value);
        }
      }
    } catch (error) {
      console.error("Failed to fetch periods:", error);
      setError(locale === "zh" ? "無法載入學年學期選項" : "Failed to load period options");
    } finally {
      setIsLoadingPeriods(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const response = await apiClient.batchImport.getHistory({ limit: 10 });
      if (response.success && response.data) {
        setHistory(response.data.items);
      }
    } catch (error) {
      console.error("Failed to fetch import history:", error);
    }
  };

  const handleFileSelect = (file: File) => {
    const validExtensions = [".xlsx", ".xls", ".csv"];
    const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf("."));

    if (!validExtensions.includes(fileExtension)) {
      setError(locale === "zh" ? "請選擇 Excel (.xlsx, .xls) 或 CSV (.csv) 檔案" : "Please select Excel (.xlsx, .xls) or CSV (.csv) file");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      setError(locale === "zh" ? "檔案大小不能超過 10MB" : "File size cannot exceed 10MB");
      return;
    }

    setSelectedFile(file);
    setError(null);
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      handleFileSelect(file);
    }
  }, []);

  const handleDownloadTemplate = async () => {
    if (!selectedScholarship) {
      setError(locale === "zh" ? "請先選擇獎學金類型" : "Please select scholarship type first");
      return;
    }

    try {
      await apiClient.batchImport.downloadTemplate(selectedScholarship.code);
    } catch (error: any) {
      setError(error.message || (locale === "zh" ? "下載範例檔案失敗" : "Failed to download template"));
    }
  };

  const handleUpload = async () => {
    if (!selectedFile || !selectedScholarship || !selectedPeriod) {
      setError(locale === "zh" ? "請選擇檔案、獎學金類型和學年學期" : "Please select file, scholarship type and period");
      return;
    }

    setIsUploading(true);
    setError(null);

    // Parse academic year and semester from selected period
    const periodParts = selectedPeriod.split("-");
    const academicYear = parseInt(periodParts[0]);
    const semester = periodParts.length > 1 ? periodParts[1] : undefined;

    try {
      const response = await apiClient.batchImport.uploadData(
        selectedFile,
        selectedScholarship.code,
        academicYear,
        semester || ""
      );

      if (response.success && response.data) {
        setUploadedBatch(response.data);
        setSelectedFile(null);
      } else {
        setError(response.message || (locale === "zh" ? "上傳失敗" : "Upload failed"));
      }
    } catch (error: any) {
      setError(error.message || (locale === "zh" ? "上傳時發生錯誤" : "Error during upload"));
    } finally {
      setIsUploading(false);
    }
  };

  const handleConfirm = async () => {
    if (!uploadedBatch) return;

    setIsConfirming(true);
    setError(null);

    try {
      const response = await apiClient.batchImport.confirm(uploadedBatch.batch_id, true);

      if (response.success && response.data) {
        alert(
          locale === "zh"
            ? `匯入完成！成功: ${response.data.success_count}, 失敗: ${response.data.failed_count}`
            : `Import complete! Success: ${response.data.success_count}, Failed: ${response.data.failed_count}`
        );
        setUploadedBatch(null);
        fetchHistory();
      } else {
        setError(response.message || (locale === "zh" ? "確認匯入失敗" : "Confirm import failed"));
      }
    } catch (error: any) {
      setError(error.message || (locale === "zh" ? "確認時發生錯誤" : "Error during confirmation"));
    } finally {
      setIsConfirming(false);
    }
  };

  const handleCancel = () => {
    setUploadedBatch(null);
    setSelectedFile(null);
    setError(null);
  };

  const renderPreviewTable = () => {
    if (!uploadedBatch || uploadedBatch.preview_data.length === 0) return null;

    const columns = Object.keys(uploadedBatch.preview_data[0]);

    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-nycu-blue-50">
              {columns.map((col) => (
                <th key={col} className="border border-nycu-blue-200 px-4 py-2 text-left text-sm font-semibold">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {uploadedBatch.preview_data.map((row, idx) => (
              <tr key={idx} className="hover:bg-gray-50">
                {columns.map((col) => (
                  <td key={col} className="border border-gray-200 px-4 py-2 text-sm">
                    {typeof row[col] === 'object' && row[col] !== null
                      ? JSON.stringify(row[col])
                      : row[col] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Upload Section */}
      {!uploadedBatch && (
        <Card className="border-nycu-blue-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
              <Upload className="h-5 w-5 text-nycu-blue-600" />
              {locale === "zh" ? "批次匯入申請資料" : "Batch Import Applications"}
            </CardTitle>
            <CardDescription>
              {locale === "zh" ? "上傳 Excel 或 CSV 檔案批次匯入學生申請資料" : "Upload Excel or CSV file to batch import student applications"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Scholarship and Period Selection */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {locale === "zh" ? "獎學金類型" : "Scholarship Type"} <span className="text-red-500">*</span>
                </label>
                {isLoadingScholarships ? (
                  <div className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-md">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm text-gray-500">{locale === "zh" ? "載入中..." : "Loading..."}</span>
                  </div>
                ) : (
                  <select
                    value={selectedScholarship?.code || ""}
                    onChange={(e) => {
                      const scholarship = scholarships.find((s) => s.code === e.target.value) || null;
                      setSelectedScholarship(scholarship);
                    }}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md"
                  >
                    <option value="">{locale === "zh" ? "請選擇獎學金" : "Select Scholarship"}</option>
                    {scholarships.map((s) => (
                      <option key={s.id} value={s.code}>
                        {s.name} ({s.code})
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {locale === "zh" ? (cycle === "yearly" ? "學年度" : "學年學期") : (cycle === "yearly" ? "Academic Year" : "Academic Period")} <span className="text-red-500">*</span>
                </label>
                {isLoadingPeriods ? (
                  <div className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-md">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm text-gray-500">{locale === "zh" ? "載入中..." : "Loading..."}</span>
                  </div>
                ) : (
                  <select
                    value={selectedPeriod}
                    onChange={(e) => setSelectedPeriod(e.target.value)}
                    disabled={!selectedScholarship}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md disabled:bg-gray-100"
                  >
                    <option value="">{locale === "zh" ? "請選擇" : "Select"}</option>
                    {periods.map((p) => (
                      <option key={p.value} value={p.value}>
                        {locale === "zh" ? p.label : p.label_en}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            {/* File Upload Area */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                isDragging ? "border-nycu-blue-600 bg-nycu-blue-50" : "border-gray-300"
              }`}
            >
              <FileSpreadsheet className="h-12 w-12 mx-auto mb-4 text-gray-400" />
              {selectedFile ? (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-gray-700">{selectedFile.name}</p>
                  <p className="text-xs text-gray-500">
                    {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                  <Button variant="outline" size="sm" onClick={() => setSelectedFile(null)}>
                    <X className="h-4 w-4 mr-2" />
                    {locale === "zh" ? "移除" : "Remove"}
                  </Button>
                </div>
              ) : (
                <>
                  <p className="text-sm text-gray-600 mb-2">
                    {locale === "zh" ? "拖放檔案至此，或點擊選擇檔案" : "Drag and drop file here, or click to select"}
                  </p>
                  <input
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleFileSelect(file);
                    }}
                    className="hidden"
                    id="file-upload"
                  />
                  <label htmlFor="file-upload">
                    <Button variant="outline" size="sm" asChild>
                      <span>
                        <Upload className="h-4 w-4 mr-2" />
                        {locale === "zh" ? "選擇檔案" : "Select File"}
                      </span>
                    </Button>
                  </label>
                  <p className="text-xs text-gray-500 mt-2">
                    {locale === "zh" ? "支援格式: .xlsx, .xls, .csv (最大 10MB)" : "Supported formats: .xlsx, .xls, .csv (max 10MB)"}
                  </p>
                </>
              )}
            </div>

            {/* Error Display */}
            {error && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Action Buttons */}
            <div className="flex gap-3">
              <Button
                onClick={handleUpload}
                disabled={!selectedFile || !selectedScholarship || !selectedPeriod || isUploading}
                className="flex-1"
              >
                {isUploading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    {locale === "zh" ? "上傳中..." : "Uploading..."}
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4 mr-2" />
                    {locale === "zh" ? "上傳並驗證" : "Upload & Validate"}
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                onClick={handleDownloadTemplate}
                disabled={!selectedScholarship}
              >
                <Download className="h-4 w-4 mr-2" />
                {locale === "zh" ? "下載範例" : "Download Template"}
              </Button>
              <Button variant="outline" onClick={() => setShowHistory(!showHistory)}>
                <History className="h-4 w-4 mr-2" />
                {locale === "zh" ? "歷史紀錄" : "History"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Preview and Validation Section */}
      {uploadedBatch && (
        <Card className="border-nycu-blue-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
              <Eye className="h-5 w-5 text-nycu-blue-600" />
              {locale === "zh" ? "資料預覽與驗證" : "Data Preview & Validation"}
            </CardTitle>
            <CardDescription>
              {locale === "zh" ? `檔案: ${uploadedBatch.file_name} (共 ${uploadedBatch.total_records} 筆)` : `File: ${uploadedBatch.file_name} (${uploadedBatch.total_records} records)`}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Validation Summary */}
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <div className="flex items-center gap-2 text-green-700 mb-1">
                  <CheckCircle className="h-5 w-5" />
                  <span className="font-semibold">{locale === "zh" ? "有效" : "Valid"}</span>
                </div>
                <p className="text-2xl font-bold text-green-800">{uploadedBatch.validation_summary.valid_count}</p>
              </div>
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex items-center gap-2 text-red-700 mb-1">
                  <XCircle className="h-5 w-5" />
                  <span className="font-semibold">{locale === "zh" ? "無效" : "Invalid"}</span>
                </div>
                <p className="text-2xl font-bold text-red-800">{uploadedBatch.validation_summary.invalid_count}</p>
              </div>
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <div className="flex items-center gap-2 text-yellow-700 mb-1">
                  <AlertTriangle className="h-5 w-5" />
                  <span className="font-semibold">{locale === "zh" ? "警告" : "Warnings"}</span>
                </div>
                <p className="text-2xl font-bold text-yellow-800">{uploadedBatch.validation_summary.warnings.length}</p>
              </div>
            </div>

            {/* Errors Display */}
            {uploadedBatch.validation_summary.errors.length > 0 && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  <div className="font-semibold mb-2">{locale === "zh" ? "驗證錯誤:" : "Validation Errors:"}</div>
                  <ul className="list-disc list-inside space-y-1 text-sm">
                    {uploadedBatch.validation_summary.errors.slice(0, 5).map((err, idx) => (
                      <li key={idx}>
                        {locale === "zh" ? "第" : "Row"} {err.row} {locale === "zh" ? "行" : ""}{err.field ? ` (${err.field})` : ""}: {err.message}
                      </li>
                    ))}
                    {uploadedBatch.validation_summary.errors.length > 5 && (
                      <li className="text-gray-600">
                        {locale === "zh" ? `...還有 ${uploadedBatch.validation_summary.errors.length - 5} 個錯誤` : `...and ${uploadedBatch.validation_summary.errors.length - 5} more errors`}
                      </li>
                    )}
                  </ul>
                </AlertDescription>
              </Alert>
            )}

            {/* Warnings Display */}
            {uploadedBatch.validation_summary.warnings.length > 0 && (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  <div className="font-semibold mb-2">{locale === "zh" ? "警告訊息:" : "Warnings:"}</div>
                  <ul className="list-disc list-inside space-y-1 text-sm">
                    {uploadedBatch.validation_summary.warnings.map((warning, idx) => (
                      <li key={idx}>{warning}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}

            {/* Preview Table */}
            <div>
              <h3 className="font-semibold text-gray-700 mb-2">
                {locale === "zh" ? "資料預覽 (前 10 筆)" : "Data Preview (First 10 rows)"}
              </h3>
              {renderPreviewTable()}
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <Button
                onClick={handleConfirm}
                disabled={uploadedBatch.validation_summary.invalid_count > 0 || isConfirming}
                className="flex-1"
              >
                {isConfirming ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    {locale === "zh" ? "匯入中..." : "Importing..."}
                  </>
                ) : (
                  <>
                    <CheckCircle className="h-4 w-4 mr-2" />
                    {locale === "zh" ? "確認匯入" : "Confirm Import"}
                  </>
                )}
              </Button>
              <Button variant="outline" onClick={handleCancel} disabled={isConfirming}>
                <XCircle className="h-4 w-4 mr-2" />
                {locale === "zh" ? "取消" : "Cancel"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Import History */}
      {showHistory && (
        <Card className="border-nycu-blue-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
              <History className="h-5 w-5 text-nycu-blue-600" />
              {locale === "zh" ? "匯入歷史紀錄" : "Import History"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {history.length === 0 ? (
              <p className="text-center text-gray-500 py-8">{locale === "zh" ? "暫無匯入紀錄" : "No import history"}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="bg-gray-50 border-b">
                      <th className="px-4 py-2 text-left text-sm font-semibold">{locale === "zh" ? "檔案名稱" : "File Name"}</th>
                      <th className="px-4 py-2 text-left text-sm font-semibold">{locale === "zh" ? "上傳時間" : "Upload Time"}</th>
                      <th className="px-4 py-2 text-left text-sm font-semibold">{locale === "zh" ? "總筆數" : "Total"}</th>
                      <th className="px-4 py-2 text-left text-sm font-semibold">{locale === "zh" ? "成功" : "Success"}</th>
                      <th className="px-4 py-2 text-left text-sm font-semibold">{locale === "zh" ? "失敗" : "Failed"}</th>
                      <th className="px-4 py-2 text-left text-sm font-semibold">{locale === "zh" ? "狀態" : "Status"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item) => (
                      <tr key={item.id} className="border-b hover:bg-gray-50">
                        <td className="px-4 py-2 text-sm">{item.file_name}</td>
                        <td className="px-4 py-2 text-sm">{new Date(item.uploaded_at).toLocaleString()}</td>
                        <td className="px-4 py-2 text-sm">{item.total_records}</td>
                        <td className="px-4 py-2 text-sm text-green-600">{item.success_count}</td>
                        <td className="px-4 py-2 text-sm text-red-600">{item.failed_count}</td>
                        <td className="px-4 py-2 text-sm">
                          <span
                            className={`px-2 py-1 rounded text-xs font-semibold ${
                              item.status === "completed"
                                ? "bg-green-100 text-green-800"
                                : item.status === "failed"
                                ? "bg-red-100 text-red-800"
                                : "bg-yellow-100 text-yellow-800"
                            }`}
                          >
                            {item.status === "completed" ? (locale === "zh" ? "完成" : "Completed") : item.status === "failed" ? (locale === "zh" ? "失敗" : "Failed") : (locale === "zh" ? "待處理" : "Pending")}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
