"use client";

import { AdminRuleManagement } from "@/components/admin-rule-management";
import { Card, CardContent } from "@/components/ui/card";
import { AlertCircle } from "lucide-react";
import { useEffect, useState } from "react";
import apiClient from "@/lib/api";
import { useAdminManagement } from "@/contexts/admin-management-context";

export function RulesPanel() {
  const { activeTab } = useAdminManagement();
  const [scholarshipTypes, setScholarshipTypes] = useState<any[]>([]);
  const [loadingScholarshipTypes, setLoadingScholarshipTypes] = useState(false);

  useEffect(() => {
    if (activeTab === "rules") {
      fetchScholarshipTypes();
    }
  }, [activeTab]);

  const fetchScholarshipTypes = async () => {
    setLoadingScholarshipTypes(true);
    try {
      const response = await apiClient.admin.getMyScholarships();
      if (response.success && response.data) {
        setScholarshipTypes(response.data);
      }
    } catch (error) {
      console.error("Failed to load scholarship types:", error);
    } finally {
      setLoadingScholarshipTypes(false);
    }
  };

  return (
    <div className="space-y-4">
      {loadingScholarshipTypes ? (
        <Card>
          <CardContent className="flex items-center justify-center py-8">
            <div className="flex items-center gap-3">
              <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
              <span className="text-nycu-navy-600">載入獎學金類型中...</span>
            </div>
          </CardContent>
        </Card>
      ) : scholarshipTypes.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <AlertCircle className="h-16 w-16 mx-auto mb-4 text-gray-300" />
            <p className="text-lg font-medium text-gray-600 mb-2">
              沒有可管理的獎學金
            </p>
            <p className="text-sm text-gray-500">
              請聯繫系統管理員分配獎學金管理權限
            </p>
          </CardContent>
        </Card>
      ) : (
        <AdminRuleManagement scholarshipTypes={scholarshipTypes} />
      )}
    </div>
  );
}
