"use client";

import useSWR from "swr";
import { useState, useEffect } from "react";
import apiClient, { type ScholarshipConfiguration } from "@/lib/api";
import { useAdminManagement } from "@/contexts/admin-management-context";

export function useWorkflows() {
  const { activeTab } = useAdminManagement();
  const [selectedConfigurationId, setSelectedConfigurationId] = useState<
    number | null
  >(null);

  // Fetch scholarship configurations with SWR
  const {
    data: configurations = [],
    isLoading,
    error,
  } = useSWR(
    activeTab === "workflows" ? "scholarshipConfigurations" : null,
    async () => {
      const response = await apiClient.admin.getScholarshipConfigurations();
      if (response.success && response.data) {
        return response.data as ScholarshipConfiguration[];
      }
      throw new Error(response.message || "Failed to load configurations");
    },
    {
      revalidateOnFocus: false,
    }
  );

  // Auto-select first configuration if none selected
  useEffect(() => {
    if (configurations.length > 0 && !selectedConfigurationId) {
      setSelectedConfigurationId(configurations[0].id);
    }
  }, [configurations, selectedConfigurationId]);

  return {
    configurations,
    selectedConfigurationId,
    setSelectedConfigurationId,
    isLoading,
    error: error?.message || null,
  };
}
