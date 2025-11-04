/**
 * Custom SWR hook for scholarship data with translations
 *
 * Provides centralized access to:
 * - All scholarships with Chinese and English names
 * - Sub-type translations (Chinese and English)
 *
 * Features:
 * - Automatic caching (24-hour revalidation interval)
 * - Singleton pattern ensures only one request per session
 * - Type-safe responses with fallback to empty data
 * - Helper functions for common queries
 * - Support for both college and admin roles
 */

import useSWR from 'swr';
import { apiClient } from '@/lib/api';
import type { ApiResponse } from '@/lib/api/types';

type ScholarshipData = Array<{
  id: number;
  code: string;
  name: string;
  name_en?: string;
  description?: string;
  status?: string;
}>;

type SubTypeTranslations = {
  zh: { [key: string]: string };
  en: { [key: string]: string };
};

type ScholarshipDataAll = {
  scholarships: ScholarshipData;
  subTypeTranslations: SubTypeTranslations;
};

/**
 * Map user role to API endpoint type
 * Returns the most appropriate API endpoint for the given role
 */
const getRoleApiType = (role?: string): 'admin' | 'college' => {
  if (!role) return 'admin'; // default fallback

  const roleStr = String(role).toLowerCase();

  // College and related roles use college API
  if (roleStr.includes('college') || roleStr === 'college') {
    return 'college';
  }

  // Admin, super_admin, and others use admin API
  return 'admin';
};

/**
 * Fetcher function for SWR
 * Combines scholarship list and sub-type translations in one request
 * Automatically selects API based on current user role
 */
const fetchAllScholarshipData = async (userRole?: string): Promise<ScholarshipDataAll> => {
  try {
    // Fetch scholarships (same for all roles)
    const scholarshipsResponse = await apiClient.scholarships.getAll();
    const scholarships = scholarshipsResponse?.data || [];

    // Fetch sub-type translations based on user role
    let subTypeTranslations: SubTypeTranslations = { zh: {}, en: {} };

    try {
      const apiType = getRoleApiType(userRole);

      if (apiType === 'college') {
        // Use college API for college users
        const translationsResponse = await apiClient.college.getSubTypeTranslations();
        if (translationsResponse?.data) {
          subTypeTranslations = {
            zh: translationsResponse.data.zh || {},
            en: translationsResponse.data.en || {},
          };
        }
      } else {
        // Use admin API for admin/super_admin users
        const translationsResponse = await apiClient.admin.getSubTypeTranslations();
        if (translationsResponse?.data) {
          subTypeTranslations = {
            zh: translationsResponse.data.zh || {},
            en: translationsResponse.data.en || {},
          };
        }
      }
    } catch (translationError) {
      console.warn('Failed to fetch sub-type translations, using empty translations', translationError);
      // Continue with empty translations rather than failing the whole request
    }

    return {
      scholarships,
      subTypeTranslations,
    };
  } catch (error) {
    console.error('Failed to fetch scholarship data:', error);
    // Return empty data instead of throwing
    return {
      scholarships: [],
      subTypeTranslations: { zh: {}, en: {} },
    };
  }
};

/**
 * Custom hook for all scholarship data with SWR
 *
 * Automatically detects current user role and fetches appropriate translation API.
 * Works for all user roles: student, professor, college, admin, super_admin
 *
 * @param autoDetectRole - If true (default), automatically detects user role from auth context.
 *                         If false, must pass explicit role parameter.
 * @param explicitRole - Optional explicit role override ('admin' or 'college')
 * @returns Scholarship data with loading and error states
 * @example
 * // Auto-detect role (recommended)
 * const { scholarships, subTypeTranslations, isLoading } = useScholarshipData();
 *
 * // Or manually specify role
 * const data = useScholarshipData(true, 'admin');
 */
export function useScholarshipData(autoDetectRole: boolean = true, explicitRole?: 'admin' | 'college') {
  // Auto-detect user role if enabled
  let userRole: string | undefined;

  try {
    // Import useAuth hook dynamically to avoid issues if used outside AuthProvider
    if (autoDetectRole) {
      // We'll try to get the role from auth, but if it fails, we'll use a safe default
      // Note: This is a bit of a workaround - ideally this would be passed in context
      const roleFromStorage = typeof window !== 'undefined'
        ? (() => {
            try {
              const user = localStorage.getItem('user') || localStorage.getItem('dev_user');
              if (user) {
                return JSON.parse(user).role;
              }
            } catch (e) {
              // Silently fail - will use default
            }
            return undefined;
          })()
        : undefined;

      userRole = roleFromStorage || explicitRole || 'admin';
    } else {
      userRole = explicitRole || 'admin';
    }
  } catch (error) {
    console.warn('Failed to detect user role, using default API', error);
    userRole = explicitRole || 'admin';
  }

  const {
    data,
    error,
    isLoading,
    mutate,
  } = useSWR(
    // Unique key for this data (include role to differentiate between admin and college)
    `scholarship-data-${userRole}`,
    // Fetcher function
    () => fetchAllScholarshipData(userRole),
    {
      // Revalidate every 24 hours (scholarships don't change frequently)
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
      dedupingInterval: 86400000, // 24 hours

      // Keep previous data while revalidating
      keepPreviousData: true,

      // Retry on error (exponential backoff)
      shouldRetryOnError: true,
      errorRetryCount: 3,
      errorRetryInterval: 5000,
    }
  );

  return {
    // Individual data arrays with fallback to empty arrays
    scholarships: data?.scholarships || [],
    subTypeTranslations: data?.subTypeTranslations || { zh: {}, en: {} },

    // Full data object
    data,

    // Loading state (initial fetch)
    isLoading,

    // Error state
    error,

    // Manual refresh function
    refresh: mutate,

    // Helper functions
    getScholarshipName: (scholarshipId: number | undefined, locale: 'zh' | 'en' = 'zh'): string => {
      if (!scholarshipId) return '-';
      const scholarship = data?.scholarships?.find(s => s.id === scholarshipId);
      if (!scholarship) return `-`;
      return locale === 'zh' ? scholarship.name : (scholarship.name_en || scholarship.name);
    },

    getScholarshipByCode: (code: string) => {
      if (!code) return null;
      return data?.scholarships?.find(s => s.code === code) || null;
    },

    getScholarshipById: (id: number) => {
      if (!id) return null;
      return data?.scholarships?.find(s => s.id === id) || null;
    },

    getSubTypeName: (subTypeCode: string | undefined, locale: 'zh' | 'en' = 'zh'): string => {
      if (!subTypeCode) return '-';
      const translations = data?.subTypeTranslations?.[locale] || {};
      return translations[subTypeCode] || subTypeCode;
    },

    getAllSubTypeNames: (locale: 'zh' | 'en' = 'zh'): { [key: string]: string } => {
      return data?.subTypeTranslations?.[locale] || {};
    },
  };
}

/**
 * Helper to get scholarship name by ID
 *
 * @param scholarshipId - The scholarship ID to look up
 * @param scholarships - Array of scholarships (from useScholarshipData)
 * @param locale - Display language ('zh' or 'en')
 * @returns Display name or fallback message
 * @example
 * const name = getScholarshipName(1, scholarships, 'zh');
 * // Returns: "學術卓越獎學金"
 */
export function getScholarshipName(
  scholarshipId: number | undefined,
  scholarships: ScholarshipData,
  locale: 'zh' | 'en' = 'zh'
): string {
  if (!scholarshipId) {
    return '-';
  }

  const scholarship = scholarships.find(s => s.id === scholarshipId);
  if (scholarship) {
    return locale === 'zh' ? scholarship.name : (scholarship.name_en || scholarship.name);
  }

  return `未知獎學金 (${scholarshipId})`;
}

/**
 * Helper to get sub-type name by code
 *
 * @param subTypeCode - The sub-type code to look up
 * @param translations - Translation object (from useScholarshipData)
 * @param locale - Display language ('zh' or 'en')
 * @returns Display name or the original code
 * @example
 * const name = getSubTypeName('domestic', translations, 'zh');
 * // Returns: "國內學生" or "domestic" if not found
 */
export function getSubTypeName(
  subTypeCode: string | undefined,
  translations: SubTypeTranslations,
  locale: 'zh' | 'en' = 'zh'
): string {
  if (!subTypeCode) {
    return '-';
  }

  const translationMap = translations[locale] || {};
  return translationMap[subTypeCode] || subTypeCode;
}

/**
 * Helper to batch translate sub-type codes
 *
 * @param codes - Array of sub-type codes to translate
 * @param translations - Translation object (from useScholarshipData)
 * @param locale - Display language ('zh' or 'en')
 * @returns Array of translated names
 * @example
 * const names = batchTranslateSubTypes(['domestic', 'overseas'], translations, 'zh');
 * // Returns: ["國內學生", "海外學生"]
 */
export function batchTranslateSubTypes(
  codes: string[],
  translations: SubTypeTranslations,
  locale: 'zh' | 'en' = 'zh'
): string[] {
  const translationMap = translations[locale] || {};
  return codes.map(code => translationMap[code] || code);
}
