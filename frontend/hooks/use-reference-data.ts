/**
 * Custom SWR hook for reference data fetching
 *
 * Provides centralized access to system reference data:
 * - Degrees, identities, studying statuses, school identities
 * - Academies, departments, enrollment types
 *
 * Features:
 * - Automatic caching (24-hour revalidation interval)
 * - Singleton pattern ensures only one request per session
 * - Type-safe responses with fallback to empty arrays
 * - Error handling and loading states
 */

import useSWR from 'swr';
import { api } from '@/lib/api';
import type { ApiResponse } from '@/lib/api.legacy';

type ReferenceDataAll = {
  academies: Array<{ id: number; code: string; name: string }>;
  departments: Array<{ id: number; code: string; name: string; academy_code?: string | null }>;
  degrees: Array<{ id: number; name: string }>;
  identities: Array<{ id: number; name: string }>;
  studying_statuses: Array<{ id: number; name: string }>;
  school_identities: Array<{ id: number; name: string }>;
  genders: Array<{ id: number; name: string }>;
  enroll_types: Array<{
    degree_id: number;
    code: string;
    name: string;
    name_en?: string;
    degree_name?: string;
  }>;
};

/**
 * Fetcher function for SWR
 */
const fetchAllReferenceData = async (): Promise<ReferenceDataAll> => {
  const response = await api.referenceData.getAll() as any;

  // Handle ApiResponse format
  if (response?.data) {
    return response.data as ReferenceDataAll;
  }

  // Fallback if response is already the data
  return response as ReferenceDataAll;
};

/**
 * Custom hook for all reference data with SWR
 *
 * @returns Reference data with loading and error states
 * @example
 * const { studyingStatuses, degrees, isLoading, error } = useReferenceData();
 */
export function useReferenceData() {
  const {
    data,
    error,
    isLoading,
    mutate,
  } = useSWR(
    // Unique key for this data
    'reference-data-all',
    // Fetcher function
    fetchAllReferenceData,
    {
      // Revalidate every 24 hours (no need to refetch frequently)
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
    degrees: data?.degrees || [],
    identities: data?.identities || [],
    studyingStatuses: data?.studying_statuses || [],
    schoolIdentities: data?.school_identities || [],
    genders: data?.genders || [],
    academies: data?.academies || [],
    departments: data?.departments || [],
    enrollTypes: data?.enroll_types || [],

    // Full data object
    data,

    // Loading state (initial fetch)
    isLoading,

    // Error state
    error,

    // Manual refresh function
    refresh: mutate,
  };
}

/**
 * Helper to get studying status name by ID
 *
 * @param statusId - The status ID to look up
 * @param statuses - Array of statuses (from useReferenceData)
 * @returns Display name or fallback message
 * @example
 * const name = getStudyingStatusName(1, studyingStatuses);
 * // Returns: "在學"
 */
export function getStudyingStatusName(
  statusId: number | undefined,
  statuses: Array<{ id: number; name: string }>
): string {
  if (statusId === undefined || statusId === null) {
    return '-';
  }

  const status = statuses.find(s => s.id === statusId);
  if (status) {
    return status.name;
  }

  return `未知狀態 (${statusId})`;
}

/**
 * Helper to get degree name by ID
 *
 * @param degreeId - The degree ID to look up
 * @param degrees - Array of degrees (from useReferenceData)
 * @returns Display name or fallback message
 */
export function getDegreeName(
  degreeId: number | undefined,
  degrees: Array<{ id: number; name: string }>
): string {
  if (degreeId === undefined || degreeId === null) {
    return '-';
  }

  const degree = degrees.find(d => d.id === degreeId);
  if (degree) {
    return degree.name;
  }

  return `未知學位 (${degreeId})`;
}

/**
 * Helper to get identity name by ID
 *
 * @param identityId - The identity ID to look up
 * @param identities - Array of identities (from useReferenceData)
 * @returns Display name or fallback message
 */
export function getIdentityName(
  identityId: number | undefined,
  identities: Array<{ id: number; name: string }>
): string {
  if (identityId === undefined || identityId === null) {
    return '-';
  }

  const identity = identities.find(i => i.id === identityId);
  if (identity) {
    return identity.name;
  }

  return `未知身份 (${identityId})`;
}

/**
 * Helper to get school identity name by ID
 *
 * @param schoolIdentityId - The school identity ID to look up
 * @param schoolIdentities - Array of school identities (from useReferenceData)
 * @returns Display name or fallback message
 */
export function getSchoolIdentityName(
  schoolIdentityId: number | undefined,
  schoolIdentities: Array<{ id: number; name: string }>
): string {
  if (schoolIdentityId === undefined || schoolIdentityId === null) {
    return '-';
  }

  const schoolIdentity = schoolIdentities.find(si => si.id === schoolIdentityId);
  if (schoolIdentity) {
    return schoolIdentity.name;
  }

  return `未知學校身份 (${schoolIdentityId})`;
}

/**
 * Helper to get academy/college name by code
 *
 * @param academyCode - The academy code to look up
 * @param academies - Array of academies (from useReferenceData)
 * @returns Display name or fallback message
 * @example
 * const name = getAcademyName("C", academies);
 * // Returns: "資訊學院"
 */
export function getAcademyName(
  academyCode: string | undefined | null,
  academies: Array<{ code: string; name: string }>
): string {
  if (!academyCode) {
    return '-';
  }

  const academy = academies.find(a => a.code === academyCode);
  if (academy) {
    return academy.name;
  }

  return academyCode;
}

/**
 * Helper to get department name by code
 *
 * @param deptCode - The department code to look up
 * @param departments - Array of departments (from useReferenceData)
 * @returns Display name or fallback message
 * @example
 * const name = getDepartmentName("4551", departments);
 * // Returns: "資訊工程學系"
 */
export function getDepartmentName(
  deptCode: string | undefined | null,
  departments: Array<{ code: string; name: string }>
): string {
  if (!deptCode) {
    return '-';
  }

  const department = departments.find(d => d.code === deptCode);
  if (department) {
    return department.name;
  }

  return deptCode;
}

/**
 * Helper to get gender name by ID
 *
 * @param genderId - The gender ID to look up (1: 男性, 2: 女性)
 * @param genders - Array of genders (from useReferenceData)
 * @returns Display name or fallback message
 * @example
 * const name = getGenderName(1, genders);
 * // Returns: "男性"
 */
export function getGenderName(
  genderId: number | undefined,
  genders: Array<{ id: number; name: string }>
): string {
  if (genderId === undefined || genderId === null) {
    return '-';
  }

  const gender = genders.find(g => g.id === genderId);
  if (gender) {
    return gender.name;
  }

  return `未知性別 (${genderId})`;
}

/**
 * Helper to get enrollment type name by code and degree
 *
 * @param enrollTypeCode - The enrollment type code to look up
 * @param degreeId - The degree ID (1: PhD, 2: Master, 3: Undergraduate, etc.) to filter enrollment types
 * @param enrollTypes - Array of enrollment types (from useReferenceData)
 * @returns Display name or fallback message
 * @example
 * const name = getEnrollTypeName(1, 3, enrollTypes);
 * // Returns: "一般入學" (for undergraduate)
 */
export function getEnrollTypeName(
  enrollTypeCode: number | undefined,
  degreeId: number | undefined,
  enrollTypes: Array<{ degree_id: number; code: string; name: string; name_en?: string; degree_name?: string }>
): string {
  if (enrollTypeCode === undefined || enrollTypeCode === null) {
    return '-';
  }

  // enrollTypes uses code (string) as lookup, but std_enrolltype is a number
  // Try to find by matching both the numeric code and degree_id
  let enrollType = enrollTypes.find((et) => {
    try {
      return parseInt(et.code, 10) === enrollTypeCode && et.degree_id === degreeId;
    } catch {
      return false;
    }
  });

  // Fallback: if degree_id is provided but no match found, try code-only lookup
  if (!enrollType && degreeId !== undefined && degreeId !== null) {
    enrollType = enrollTypes.find((et) => {
      try {
        return parseInt(et.code, 10) === enrollTypeCode;
      } catch {
        return false;
      }
    });
  }

  if (enrollType) {
    return enrollType.name;
  }

  return `未知入學方式 (${enrollTypeCode})`;
}
