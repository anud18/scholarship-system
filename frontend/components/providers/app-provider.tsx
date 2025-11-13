"use client";

import { SWRConfig } from "swr";
import { apiClient } from "@/lib/api";
import { AuthProvider } from "@/hooks/use-auth";
import { NotificationProvider } from "@/contexts/notification-context";

/**
 * Unified App Provider
 *
 * Combines SWR, Auth, and Notification providers into a single component
 * to reduce provider nesting and improve bundle efficiency.
 */

const defaultFetcher = async (endpoint: string) => {
  const response = await apiClient.request(endpoint);
  if (!response.success) {
    throw new Error(response.message || "Request failed");
  }
  return response.data ?? null;
};

export function AppProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        fetcher: defaultFetcher,
        revalidateOnFocus: true,
        shouldRetryOnError: false,
      }}
    >
      <AuthProvider>
        <NotificationProvider>{children}</NotificationProvider>
      </AuthProvider>
    </SWRConfig>
  );
}
