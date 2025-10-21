"use client";

import React, { useEffect, useState } from "react";
import { AlertCircle, CheckCircle, Lock, Building2, Award } from "lucide-react";
import { apiClient } from "@/lib/api";
import type { User } from "@/types/user";

interface PermissionStatus {
  user_nycu_id: string;
  user_id: number;
  college_code: string | null;
  college_name: string | null;
  scholarship_count: number;
  scholarship_list: Array<{
    code: string;
    name: string;
    name_en?: string;
  }>;
  has_full_permission: boolean;
  permission_issues: string[];
}

interface PermissionStatusPanelProps {
  user: User;
  locale?: "zh" | "en";
  onRefresh?: () => void;
}

/**
 * PermissionStatusPanel
 * 顯示學院用戶的權限狀態，包括：
 * - 是否分配了學院
 * - 獲得的獎學金數量
 * - 具體的獎學金清單
 * - 權限問題診斷
 */
export function PermissionStatusPanel({
  user,
  locale = "zh",
  onRefresh,
}: PermissionStatusPanelProps) {
  const [status, setStatus] = useState<PermissionStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPermissionStatus();
  }, [user.id]);

  const fetchPermissionStatus = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Get managed college info
      const collegeResponse = await apiClient.college.getManagedCollege();

      // Get available combinations to see scholarship permissions
      const combinationsResponse = await apiClient.college.getAvailableCombinations();

      const permissionIssues: string[] = [];
      let hasFullPermission = true;

      // Check for issues
      if (!collegeResponse.data) {
        permissionIssues.push(locale === "zh" ? "未分配學院" : "No college assigned");
        hasFullPermission = false;
      }

      if (!combinationsResponse.data?.scholarship_types || combinationsResponse.data.scholarship_types.length === 0) {
        permissionIssues.push(
          locale === "zh" ? "沒有獎學金管理權限" : "No scholarship management permissions"
        );
        hasFullPermission = false;
      }

      const statusData: PermissionStatus = {
        user_nycu_id: user.nycu_id || user.name,
        user_id: typeof user.id === "string" ? parseInt(user.id, 10) : user.id,
        college_code: collegeResponse.data?.code || null,
        college_name: collegeResponse.data?.name || null,
        scholarship_count: collegeResponse.data?.scholarship_count || 0,
        scholarship_list: combinationsResponse.data?.scholarship_types || [],
        has_full_permission: hasFullPermission,
        permission_issues: permissionIssues,
      };

      setStatus(statusData);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : locale === "zh" ? "載入權限狀態失敗" : "Failed to load permission status";
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-6">
        <div className="text-gray-500">
          {locale === "zh" ? "載入權限資訊中..." : "Loading permission information..."}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-sm text-red-700">{error}</p>
      </div>
    );
  }

  if (!status) {
    return null;
  }

  const statusColor = status.has_full_permission ? "green" : "yellow";
  const statusIcon = status.has_full_permission ? CheckCircle : AlertCircle;
  const StatusIcon = statusIcon;

  return (
    <div className={`border rounded-lg overflow-hidden ${statusColor === "green" ? "border-green-200 bg-green-50" : "border-yellow-200 bg-yellow-50"}`}>
      {/* Header */}
      <div className={`px-4 py-3 border-b ${statusColor === "green" ? "border-green-200 bg-green-100" : "border-yellow-200 bg-yellow-100"}`}>
        <div className="flex items-center gap-2">
          <StatusIcon className={`h-5 w-5 ${statusColor === "green" ? "text-green-700" : "text-yellow-700"}`} />
          <h3 className={`font-semibold ${statusColor === "green" ? "text-green-900" : "text-yellow-900"}`}>
            {locale === "zh" ? "權限狀態" : "Permission Status"}
          </h3>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* User Info */}
        <div>
          <p className="text-xs font-semibold text-gray-600 uppercase mb-1">
            {locale === "zh" ? "用戶資訊" : "User Information"}
          </p>
          <p className="text-sm text-gray-800">
            <span className="font-medium">{status.user_nycu_id}</span>
            <span className="text-gray-500 ml-2">({locale === "zh" ? "ID" : "ID"}: {status.user_id})</span>
          </p>
        </div>

        {/* College Info */}
        <div>
          <p className="text-xs font-semibold text-gray-600 uppercase mb-1 flex items-center gap-1">
            <Building2 className="h-3 w-3" />
            {locale === "zh" ? "分配學院" : "Assigned College"}
          </p>
          {status.college_code ? (
            <p className="text-sm text-gray-800">
              <span className="font-medium">{status.college_name}</span>
              <span className="text-gray-500 ml-2">({status.college_code})</span>
            </p>
          ) : (
            <p className="text-sm text-red-700">
              {locale === "zh" ? "未分配" : "Not assigned"}
            </p>
          )}
        </div>

        {/* Scholarship Permissions */}
        <div>
          <p className="text-xs font-semibold text-gray-600 uppercase mb-2 flex items-center gap-1">
            <Award className="h-3 w-3" />
            {locale === "zh" ? "獎學金管理權限" : "Scholarship Management Permissions"}
          </p>
          {status.scholarship_count > 0 ? (
            <div className="space-y-1">
              <p className="text-sm text-gray-700">
                {locale === "zh" ? "已授予 " : "Authorized for "}
                <span className="font-semibold text-green-700">{status.scholarship_count}</span>
                {locale === "zh" ? " 個獎學金" : " scholarship(s)"}
              </p>
              <ul className="text-sm space-y-1 ml-2">
                {status.scholarship_list.map((scholarship, index) => (
                  <li key={index} className="text-gray-700 flex items-center gap-1">
                    <span className="text-green-600">✓</span>
                    <span className="font-medium">{scholarship.name}</span>
                    <span className="text-gray-500">({scholarship.code})</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-red-700">
              {locale === "zh" ? "沒有獎學金管理權限" : "No scholarship management permissions"}
            </p>
          )}
        </div>

        {/* Permission Issues */}
        {status.permission_issues.length > 0 && (
          <div className="p-3 bg-red-100 border border-red-300 rounded">
            <p className="text-xs font-semibold text-red-900 mb-2">
              {locale === "zh" ? "偵測到的問題：" : "Detected Issues:"}
            </p>
            <ul className="space-y-1">
              {status.permission_issues.map((issue, index) => (
                <li key={index} className="text-xs text-red-800 flex items-center gap-1">
                  <span className="text-red-600">✕</span>
                  {issue}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Help Info */}
        <div className="p-3 bg-blue-100 border border-blue-300 rounded text-xs text-blue-800">
          {locale === "zh"
            ? "如需調整權限，請聯絡系統管理員。管理員可在「系統設定 > 權限管理」中為您指派學院和獎學金權限。"
            : "To adjust permissions, please contact your system administrator. They can assign your college and scholarship permissions in \"System Settings > Permission Management\"."}
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 bg-gray-100 border-t flex justify-end">
        <button
          onClick={() => {
            fetchPermissionStatus();
            onRefresh?.();
          }}
          className="text-xs font-medium text-blue-600 hover:text-blue-700 px-3 py-1 rounded hover:bg-blue-50"
        >
          {locale === "zh" ? "重新載入" : "Refresh"}
        </button>
      </div>
    </div>
  );
}
