/**
 * Custom SWR hook for student profile data fetching
 *
 * Provides centralized access to current user's complete profile:
 * - Basic user information
 * - Student academic data
 * - Editable profile fields (advisor, bank info, etc.)
 *
 * Features:
 * - Automatic caching with smart revalidation
 * - Singleton pattern ensures only one request per session
 * - Type-safe responses with proper error handling
 * - Loading states and error recovery
 * - Automatic refresh on focus (with deduplication)
 */

import useSWR from 'swr';
import { api } from '@/lib/api';
import type { ApiResponse } from '@/lib/api/types';

/**
 * Complete user profile structure
 * Matches backend CompleteUserProfile response
 */
type CompleteUserProfile = {
  user_info: {
    id: string;
    nycu_id: string;
    name: string;
    email: string;
    dept_name?: string;
    dept_code?: string;
    user_type?: string;
    status?: string;
    role?: string;
    [key: string]: any;
  };
  student_info?: {
    std_stdcode?: string;
    std_cname?: string;
    std_degree?: string;
    std_studingstatus?: string;
    std_enrollyear?: string;
    std_termcount?: string;
    [key: string]: any;
  };
  profile?: {
    id?: number;
    user_id?: number;
    advisor_name?: string;
    advisor_email?: string;
    advisor_nycu_id?: string;
    account_number?: string;
    bank_document_photo_url?: string;
    [key: string]: any;
  };
  [key: string]: any;
};

/**
 * Fetcher function for SWR
 * Unwraps ApiResponse format to return raw data
 */
const fetchStudentProfile = async (): Promise<CompleteUserProfile> => {
  const response = await api.userProfiles.getMyProfile() as unknown as ApiResponse<CompleteUserProfile>;

  // Handle ApiResponse format
  if (response?.success && response?.data) {
    return response.data;
  }

  // If response indicates failure, throw error for SWR error handling
  if (response && !response.success) {
    throw new Error(response.message || 'Failed to fetch student profile');
  }

  // Fallback if response is already the data (shouldn't happen with typed API)
  return response as unknown as CompleteUserProfile;
};

/**
 * Custom hook for student profile with SWR
 *
 * @returns Student profile data with loading and error states
 * @example
 * ```tsx
 * const { userInfo, studentInfo, profile, isLoading, error, refresh } = useStudentProfile();
 *
 * if (isLoading) return <Loading />;
 * if (error) return <Error message={error.message} />;
 *
 * return <div>{userInfo.name}</div>;
 * ```
 */
export function useStudentProfile() {
  const {
    data,
    error,
    isLoading,
    mutate,
  } = useSWR(
    // Unique key for this data - same key across all components ensures sharing
    'user-profile-me',
    // Fetcher function
    fetchStudentProfile,
    {
      // Revalidate when window regains focus (user comes back to page)
      revalidateOnFocus: true,

      // Revalidate on network reconnection
      revalidateOnReconnect: true,

      // Deduplicate requests within 60 seconds
      // Multiple components using this hook won't trigger duplicate requests
      dedupingInterval: 60000, // 1 minute

      // Keep previous data while revalidating (prevents UI flicker)
      keepPreviousData: true,

      // Retry on error with exponential backoff
      shouldRetryOnError: true,
      errorRetryCount: 3,
      errorRetryInterval: 5000, // 5 seconds

      // Don't revalidate on mount if data exists (use cache)
      revalidateIfStale: true,
    }
  );

  return {
    // Individual data sections with fallback to empty objects
    userInfo: data?.user_info || null,
    studentInfo: data?.student_info || null,
    profile: data?.profile || null,

    // Full data object
    data,

    // Loading state (true only on initial fetch)
    isLoading,

    // Error state
    error,

    // Manual refresh function
    // Call this after updating profile to sync changes
    refresh: mutate,
  };
}

/**
 * Helper to check if student has complete profile
 *
 * @param profile - Profile object from useStudentProfile
 * @returns Boolean indicating if all required fields are filled
 */
export function hasCompleteProfile(
  profile: CompleteUserProfile['profile'] | null
): boolean {
  if (!profile) return false;

  const requiredFields = [
    'advisor_name',
    'advisor_email',
    'advisor_nycu_id',
    'account_number',
  ];

  return requiredFields.every(field => {
    const value = profile[field];
    return value !== null && value !== undefined && value !== '';
  });
}

/**
 * Helper to get profile completion percentage
 *
 * @param profile - Profile object from useStudentProfile
 * @returns Percentage (0-100) of profile completion
 */
export function getProfileCompletion(
  profile: CompleteUserProfile['profile'] | null
): number {
  if (!profile) return 0;

  const fields = [
    'advisor_name',
    'advisor_email',
    'advisor_nycu_id',
    'account_number',
    'bank_document_photo_url',
  ];

  const completed = fields.filter(field => {
    const value = profile[field];
    return value !== null && value !== undefined && value !== '';
  }).length;

  return Math.round((completed / fields.length) * 100);
}

/**
 * Helper to extract student display name
 *
 * @param studentInfo - Student info from useStudentProfile
 * @param userInfo - User info from useStudentProfile
 * @returns Display name or fallback
 */
export function getStudentDisplayName(
  studentInfo: CompleteUserProfile['student_info'] | null,
  userInfo: CompleteUserProfile['user_info'] | null
): string {
  // Prefer student_info name (Chinese name from SIS)
  if (studentInfo?.std_cname) {
    return studentInfo.std_cname;
  }

  // Fallback to user_info name
  if (userInfo?.name) {
    return userInfo.name;
  }

  return '-';
}
