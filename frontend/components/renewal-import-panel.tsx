"use client";

import React, { useState, useCallback, useEffect } from "react";
import { logger } from "@/lib/utils/logger";
import { apiClient } from "@/lib/api";

/**
 * Coerce a caught error to a user-presentable string. The `error` argument
 * is `unknown` because TypeScript widens caught values for safety; this
 * helper centralizes the narrowing so each catch block doesn't need its own
 * `instanceof Error` boilerplate.
 */
function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string" && error) return error;
  return fallback;
}
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
import { getTranslation } from "@/lib/i18n";

interface RenewalImportPanelProps {
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

type ValidationWarning =
  | {
      row?: number;
      field?: string;
      message?: string;
      warning_type?: string;
    }
  | string;

interface UploadedBatch {
  batch_id: number;
  file_name: string;
  total_records: number;
  skipped_records: number;
  preview_data: Array<Record<string, unknown>>;
  validation_summary: {
    valid_count: number;
    invalid_count: number;
    skipped_count: number;
    warnings: ValidationWarning[];
    errors: Array<{
      row: number;
      field?: string;
      message: string;
    }>;
  };
}

interface ImportHistoryItem {
  id: number;
  file_name: string;
  importer_name?: string;
  created_at: string;
  total_records: number;
  success_count: number;
  failed_count: number;
  import_status: string;
  scholarship_type_id?: number;
  college_code: string;
  academic_year: number;
  semester: string | null;
}

export function RenewalImportPanel({ locale = "zh" }: RenewalImportPanelProps) {
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

  const errorItems = uploadedBatch?.validation_summary?.errors ?? [];
  const warningItems = (uploadedBatch?.validation_summary?.warnings ?? []).map((warning) =>
    typeof warning === "string" ? { message: warning } : warning
  );

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
        setScholarships(response.data as Scholarship[]);
      }
    } catch (error) {
      logger.error("Failed to fetch scholarships", { error: error });
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
      logger.error("Failed to fetch periods", { error: error });
      setError(locale === "zh" ? "無法載入學年學期選項" : "Failed to load period options");
    } finally {
      setIsLoadingPeriods(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const response = await apiClient.renewalImport.getHistory({ limit: 10 });
      if (response.success && response.data) {
        const items = (response.data.items as ImportHistoryItem[] | undefined) ?? [];
        setHistory(items);
      }
    } catch (error) {
      logger.error("Failed to fetch renewal import history", { error: error });
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
      await apiClient.renewalImport.downloadTemplate(selectedScholarship.code);
    } catch (error) {
      setError(
        getErrorMessage(error, locale === "zh" ? "下載範例檔案失敗" : "Failed to download template")
      );
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
      const response = await apiClient.renewalImport.uploadData(
        selectedFile,
        selectedScholarship.code,
        academicYear,
        semester || ""
      );

      if (response.success && response.data) {
        setUploadedBatch(response.data as unknown as UploadedBatch);
        setSelectedFile(null);
      } else {
        setError(response.message || (locale === "zh" ? "上傳失敗" : "Upload failed"));
      }
    } catch (error) {
      setError(getErrorMessage(error, locale === "zh" ? "上傳時發生錯誤" : "Error during upload"));
    } finally {
      setIsUploading(false);
    }
  };

  const handleConfirm = async () => {
    if (!uploadedBatch) return;

    setIsConfirming(true);
    setError(null);

    try {
      const response = await apiClient.renewalImport.confirm(uploadedBatch.batch_id, true);

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
    } catch (error) {
      setError(
        getErrorMessage(error, locale === "zh" ? "確認時發生錯誤" : "Error during confirmation")
      );
    } finally {
      setIsConfirming(false);
    }
  };

  const handleCancel = () => {
    setSelectedFile(null);
    setUploadedBatch(null);
    setError(null);
    setIsUploading(false);
    setIsConfirming(false);
  };

  const renderPreviewTable = () => {
    if (!uploadedBatch || uploadedBatch.preview_data.length === 0) return null;

    const columns = Object.keys(uploadedBatch.preview_data[0]);

    // Helper function to get translated field label
    const getFieldLabel = (fieldName: string): string => {
      const translationKey = `renewal_import.field_labels.${fieldName}`;
      const translated = getTranslation(locale, translationKey);
      // If translation not found, return original field name
      return translated === translationKey ? fieldName : translated;
    };

    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-nycu-blue-50">
              <th className="border border-nycu-blue-200 px-4 py-2 text-left text-sm font-semibold">
                {locale === "zh" ? "序號" : "#"}
              </th>
              {columns.map((col) => (
                <th key={col} className="border border-nycu-blue-200 px-4 py-2 text-left text-sm font-semibold">
                  {getFieldLabel(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {uploadedBatch.preview_data.map((row, idx) => (
              <tr key={idx} className="hover:bg-gray-50">
                <td className="border border-gray-200 px-4 py-2 text-sm font-medium">
                  {locale === "zh" ? `第 ${idx + 1} 筆` : `#${idx + 1}`}
                </td>
                {columns.map((col) => {
                  const cell = row[col];
                  const display: string | number | boolean =
                    typeof cell === "object" && cell !== null
                      ? JSON.stringify(cell)
                      : (cell as string | number | boolean | null | undefined) ?? "";
                  return (
                    <td key={col} className="border border-gray-200 px-4 py-2 text-sm">
                      {display}
                    </td>
                  );
                })}
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
              {locale === "zh" ? "匯入續領生名單" : "Import Renewal Students"}
            </CardTitle>
            <CardDescription>
              {locale === "zh"
                ? "上傳 Excel 或 CSV 檔案批次匯入續領生資料（僅保留「是 + 通過」的學生）"
                : "Upload Excel or CSV file to batch import renewal students (only keeps rows marked 是 + 通過)"}
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
                    id="renewal-file-upload"
                  />
                  <label htmlFor="renewal-file-upload">
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
              {locale === "zh" ? `檔案: ${uploadedBatch.file_name}` : `File: ${uploadedBatch.file_name}`}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Summary Line */}
            <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
              <CheckCircle className="h-5 w-5 text-green-600" />
              {locale === "zh"
                ? `通過 ${uploadedBatch.total_records} 筆 · 跳過 ${uploadedBatch.skipped_records} 筆 · 錯誤 ${uploadedBatch.validation_summary.invalid_count} 筆`
                : `Passed ${uploadedBatch.total_records} · Skipped ${uploadedBatch.skipped_records} · Errors ${uploadedBatch.validation_summary.invalid_count}`}
            </div>

            {/* Errors Display */}
            {errorItems.length > 0 && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  <div className="font-semibold mb-2">{locale === "zh" ? "驗證錯誤:" : "Validation Errors:"}</div>
                  <ul className="list-disc list-inside space-y-1 text-sm">
                    {errorItems.slice(0, 5).map((err, idx) => (
                      <li key={idx}>
                        {locale === "zh" ? `第 ${err.row} 筆資料` : `Record ${err.row}`}{err.field ? ` (${err.field})` : ""}: {err.message}
                      </li>
                    ))}
                    {errorItems.length > 5 && (
                      <li className="text-gray-600">
                        {locale === "zh" ? `...還有 ${errorItems.length - 5} 個錯誤` : `...and ${errorItems.length - 5} more errors`}
                      </li>
                    )}
                  </ul>
                </AlertDescription>
              </Alert>
            )}

            {/* Warnings Display */}
            {warningItems.length > 0 && (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  <div className="font-semibold mb-2">{locale === "zh" ? "警告訊息:" : "Warnings:"}</div>
                  <ul className="list-disc list-inside space-y-1 text-sm">
                    {warningItems.map((warning, idx) => (
                      <li key={idx}>
                        {warning.message ?? (locale === "zh" ? "待確認" : "Needs verification")}
                      </li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}

            {/* Preview Table */}
            <div>
              <h3 className="font-semibold text-gray-700 mb-2">
                {locale === "zh" ? `資料預覽 (共 ${uploadedBatch.total_records} 筆)` : `Data Preview (${uploadedBatch.total_records} records)`}
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
                    {locale === "zh" ? "確認匯入續領" : "Confirm Renewal Import"}
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
                        <td className="px-4 py-2 text-sm">{new Date(item.created_at).toLocaleString()}</td>
                        <td className="px-4 py-2 text-sm">{item.total_records}</td>
                        <td className="px-4 py-2 text-sm text-green-600">{item.success_count}</td>
                        <td className="px-4 py-2 text-sm text-red-600">{item.failed_count}</td>
                        <td className="px-4 py-2 text-sm">
                          <span
                            className={`px-2 py-1 rounded text-xs font-semibold ${
                              item.import_status === "completed"
                                ? "bg-green-100 text-green-800"
                                : item.import_status === "failed"
                                ? "bg-red-100 text-red-800"
                                : "bg-yellow-100 text-yellow-800"
                            }`}
                          >
                            {item.import_status === "completed" ? (locale === "zh" ? "完成" : "Completed") : item.import_status === "failed" ? (locale === "zh" ? "失敗" : "Failed") : (locale === "zh" ? "待處理" : "Pending")}
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
