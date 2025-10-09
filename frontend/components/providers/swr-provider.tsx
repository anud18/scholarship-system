"use client";

import { SWRConfig } from "swr";
import { apiClient } from "@/lib/api";

/**
 * Client Component wrapper for SWRConfig
 *
 * This is needed because Next.js 15 doesn't allow passing functions
 * from Server Components to Client Components directly.
 */

const defaultFetcher = async (endpoint: string) => {
  const response = await apiClient.request(endpoint);
  if (!response.success) {
    throw new Error(response.message || "Request failed");
  }
  return response.data ?? null;
};

export function SWRProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        fetcher: defaultFetcher,
        revalidateOnFocus: true,
        shouldRetryOnError: false,
      }}
    >
      {children}
    </SWRConfig>
  );
}
