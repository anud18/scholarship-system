/**
 * Custom SWR hook for quota data fetching
 *
 * Provides intelligent data fetching with:
 * - Automatic refresh on window focus
 * - Network recovery handling
 * - Request deduplication
 * - Background revalidation
 */

import useSWR from 'swr';
import { quotaApi } from '@/services/api/quotaApi';
import type { MatrixQuotaData } from '@/types/quota';
import type { ApiResponse } from '@/lib/api';

/**
 * Fetcher function for SWR
 */
const fetchQuotaData = async (period: string): Promise<ApiResponse<MatrixQuotaData>> => {
  return quotaApi.getMatrixQuotaStatus(period);
};

/**
 * Custom hook for quota data with SWR
 *
 * @param period - Academic period (e.g., "113-1" or "113")
 * @param options - Optional configuration
 * @returns SWR response with data, loading, error, and refresh function
 */
export function useQuotaData(
  period: string | null,
  options?: {
    refreshInterval?: number;
    revalidateOnFocus?: boolean;
    revalidateOnReconnect?: boolean;
  }
) {
  const {
    data,
    error,
    mutate,
    isLoading,
    isValidating,
  } = useSWR(
    // Key: null if no period selected (prevents fetching)
    period ? `quota-${period}` : null,
    // Fetcher: only called when key is non-null
    () => fetchQuotaData(period!),
    {
      // Refresh every 30 seconds by default
      refreshInterval: options?.refreshInterval ?? 30000,

      // Revalidate when window regains focus
      revalidateOnFocus: options?.revalidateOnFocus ?? true,

      // Revalidate when network reconnects
      revalidateOnReconnect: options?.revalidateOnReconnect ?? true,

      // Deduplicate requests within 5 seconds
      dedupingInterval: 5000,

      // Keep previous data while revalidating
      keepPreviousData: true,

      // Retry on error (exponential backoff)
      shouldRetryOnError: true,
      errorRetryCount: 3,
      errorRetryInterval: 5000,
    }
  );

  return {
    // Quota data from API response
    data: data?.data ?? null,

    // Full API response (includes success, message)
    response: data,

    // Loading state (initial fetch)
    isLoading,

    // Refreshing state (background revalidation)
    isRefreshing: isValidating,

    // Error state
    error,

    // Manual refresh function
    refresh: mutate,
  };
}
