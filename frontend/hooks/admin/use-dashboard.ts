"use client";

import { useQuery } from "@tanstack/react-query";
import apiClient, { type SystemStats } from "@/lib/api";
import { useAdminManagement } from "@/contexts/admin-management-context";

export function useDashboard() {
  const { activeTab } = useAdminManagement();

  const {
    data: stats,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["systemStats"],
    queryFn: async () => {
      const response = await apiClient.admin.getSystemStats();
      if (response.success && response.data) {
        return response.data as SystemStats;
      }
      throw new Error(response.message || "Failed to fetch system stats");
    },
    enabled: activeTab === "dashboard",
    staleTime: 60000, // 1 minute
  });

  return {
    stats: stats ?? null,
    isLoading,
    error: error?.message || null,
    refetch,
  };
}
