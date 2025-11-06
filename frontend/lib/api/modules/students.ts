/**
 * Students API Module (OpenAPI-typed)
 *
 * Admin student management operations including:
 * - Student list with pagination and filters
 * - Student statistics
 * - Student details
 * - SIS (Student Information System) data
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';

// Type definitions
type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
};

export type Student = {
  id: number;
  nycu_id: string;
  name: string;
  email: string;
  user_type?: string;
  status?: string;
  dept_code?: string;
  dept_name?: string;
  college_code?: string;
  comment?: string;
  created_at: string;
  updated_at?: string;
  last_login_at?: string;
};

export type StudentStats = {
  total_students: number;
  status_distribution: Record<string, number>;
  dept_distribution: Record<string, number>;
  recent_registrations: number;
};

export type StudentSISBasicInfo = {
  std_stdno?: string;
  std_stdcode?: string;
  std_cname?: string;
  std_ename?: string;
  std_degree?: string;
  std_studingstatus?: string;
  std_sex?: string;
  std_depno?: string;
  std_depname?: string;
  std_aca_no?: string;
  std_aca_cname?: string;
  com_cellphone?: string;
  com_email?: string;
  [key: string]: any;
};

export type StudentSISTermData = {
  academic_year: string;
  term: string;
  trm_year?: string;
  trm_term?: string;
  trm_academyname?: string;
  trm_depname?: string;
  trm_ascore_gpa?: number;
  trm_totalcredits?: number;
  [key: string]: any;
};

export type StudentSISData = {
  basic_info: StudentSISBasicInfo;
  semesters: StudentSISTermData[];
};

export function createStudentsApi() {
  return {
    /**
     * Get all students with pagination and filters
     * Type-safe: Query parameters validated against OpenAPI
     *
     * @param params - Query parameters
     * @param params.page - Page number (default: 1)
     * @param params.size - Items per page (default: 20, max: 100)
     * @param params.search - Search by name, email, or NYCU ID
     * @param params.dept_code - Filter by department code
     * @param params.status - Filter by status (在學/畢業)
     */
    getAll: async (params?: {
      page?: number;
      size?: number;
      search?: string;
      dept_code?: string;
      status?: string;
    }): Promise<ApiResponse<PaginatedResponse<Student>>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/students', {
        params: { query: params },
      });
      return toApiResponse<PaginatedResponse<Student>>(response);
    },

    /**
     * Get student statistics
     * Type-safe: Response type inferred from OpenAPI
     *
     * Returns:
     * - total_students: Total number of students
     * - status_distribution: Distribution by status (在學/畢業)
     * - dept_distribution: Top 10 departments by student count
     * - recent_registrations: Students registered in last 30 days
     */
    getStats: async (): Promise<ApiResponse<StudentStats>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/students/stats');
      return toApiResponse<StudentStats>(response);
    },

    /**
     * Get student detail by ID
     * Type-safe: Path parameter validated against OpenAPI
     *
     * @param userId - Student user ID
     * Returns basic user info from database
     */
    getById: async (userId: number): Promise<ApiResponse<Student>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/students/{user_id}', {
        params: { path: { user_id: userId } },
      });
      return toApiResponse<Student>(response);
    },

    /**
     * Get student SIS data (real-time from Student Information System)
     * Type-safe: Path parameter validated against OpenAPI
     *
     * @param userId - Student user ID
     * Returns:
     * - basic_info: Student basic information from SIS
     * - semesters: Semester data for recent years (last 3 years)
     *
     * Note: This endpoint fetches fresh data from external SIS API.
     * May return 404 if student not found in SIS or 503 if SIS is unavailable.
     */
    getSISData: async (userId: number): Promise<ApiResponse<StudentSISData>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/students/{user_id}/sis-data', {
        params: { path: { user_id: userId } },
      });
      return toApiResponse<StudentSISData>(response);
    },
  };
}
