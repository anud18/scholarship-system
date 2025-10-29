"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import apiClient, { type ScholarshipConfiguration } from "@/lib/api";
import { useAdminManagement } from "@/contexts/admin-management-context";

export function useWorkflows() {
  const { activeTab } = useAdminManagement();
  const [selectedConfigurationId, setSelectedConfigurationId] = useState<
    number | null
  >(null);

  // Fetch scholarship configurations with React Query
  const {
    data: configurations = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ["scholarshipConfigurations"],
    queryFn: async () => {
      const response = await apiClient.admin.getScholarshipConfigurations();
      if (response.success && response.data) {
        // Auto-select first configuration if none selected
        if (response.data.length > 0 && !selectedConfigurationId) {
          setSelectedConfigurationId(response.data[0].id);
        }
        return response.data as ScholarshipConfiguration[];
      }
      throw new Error(response.message || "Failed to load configurations");
    },
    enabled: activeTab === "workflows", // Only fetch when workflows tab is active
  });

  return {
    configurations,
    selectedConfigurationId,
    setSelectedConfigurationId,
    isLoading,
    error: error?.message || null,
  };
}
