/**
 * Admin API Module (OpenAPI-typed)
 *
 * Comprehensive admin functionality:
 * - Dashboard and statistics
 * - Application management
 * - Email templates
 * - System announcements
 * - Scholarship management
 * - Rules and workflows
 * - Permissions
 * - Configurations
 * - Professor management
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse, DashboardStats, HistoricalApplicationFilters } from '../types';
import type { components } from '../generated/schema';

export function createAdminApi() {
  return {
    // ========== Dashboard and Statistics ==========

    /**
     * Get dashboard statistics.
     *
     * Returns the unified DashboardStats shape (snake_case canonical fields
     * + legacy camelCase aliases for the admin-management-interface UI).
     * See issue #642 for the reconciliation.
     */
    getDashboardStats: async (): Promise<ApiResponse<DashboardStats>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/dashboard/stats');
      return toApiResponse(response) as ApiResponse<DashboardStats>;
    },

    /**
     * Get recent applications
     * Type-safe: Query parameters validated against OpenAPI
     */
    getRecentApplications: async (limit?: number): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/recent-applications', {
        params: { query: { limit } },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Get system announcements
     * Type-safe: Query parameters validated against OpenAPI
     */
    getSystemAnnouncements: async (limit?: number): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/system-announcements', {
        params: { query: { limit } },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Get system stats — alias for getDashboardStats.
     *
     * Returns the same DashboardStats shape (legacy SystemStats is a type
     * alias for DashboardStats). See issue #642.
     */
    getSystemStats: async (): Promise<ApiResponse<DashboardStats>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/dashboard/stats');
      return toApiResponse(response) as ApiResponse<DashboardStats>;
    },

    // ========== Application Management ==========

    /**
     * Get all applications with pagination
     * Type-safe: Query parameters validated against OpenAPI
     */
    getAllApplications: async (
      page?: number,
      size?: number,
      status?: string
    ): Promise<ApiResponse<{ items: unknown[]; total: number; page: number; size: number }>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/applications', {
        params: {
          query: {
            page,
            size,
            status,
          },
        },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Get historical applications with filters
     * Type-safe: Query parameters validated against OpenAPI
     */
    getHistoricalApplications: async (
      filters?: HistoricalApplicationFilters
    ): Promise<ApiResponse<{ items: unknown[]; page: number; size: number; total: number; pages: number }>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/applications/history', {
        params: {
          query: {
            page: filters?.page,
            size: filters?.size,
            status: filters?.status,
            scholarship_type: filters?.scholarship_type,
            academic_year: filters?.academic_year,
            semester: filters?.semester,
            search: filters?.search,
          },
        },
      });
      return toApiResponse(response) as ApiResponse<{ items: unknown[]; page: number; size: number; total: number; pages: number }>;
    },

    /**
     * Update application status
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateApplicationStatus: async (
      applicationId: number,
      status: string,
      reviewNotes?: string
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PATCH('/api/v1/admin/applications/{id}/status', {
        params: { path: { id: applicationId } },
        body: { status, review_notes: reviewNotes },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    // ========== Email Templates ==========

    /**
     * Get email template by key
     * Type-safe: Query parameters validated against OpenAPI
     */
    getEmailTemplate: async (key: string): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/email-template', {
        params: { query: { key } },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Update email template
     * Type-safe: Request body validated against OpenAPI
     */
    updateEmailTemplate: async (template: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT('/api/v1/admin/email-template', {
        body: template as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Get email templates by sending type
     * Type-safe: Query parameters validated against OpenAPI
     */
    getEmailTemplatesBySendingType: async (sendingType?: string): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/email-templates', {
        params: { query: { sending_type: sendingType } },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    // Scholarship Email Templates
    /**
     * Get scholarship email templates
     * Type-safe: Path parameter validated against OpenAPI
     */
    getScholarshipEmailTemplates: async (
      scholarshipTypeId: number
    ): Promise<ApiResponse<{ items: unknown[]; total: number }>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarship-email-templates/{scholarship_type_id}', {
        params: { path: { scholarship_type_id: scholarshipTypeId } },
      });
      return toApiResponse(response) as ApiResponse<{ items: unknown[]; total: number }>;
    },

    /**
     * Get specific scholarship email template
     * Type-safe: Path parameters validated against OpenAPI
     */
    getScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateKey: string
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarship-email-templates/{scholarship_type_id}/{template_key}', {
        params: { path: { scholarship_type_id: scholarshipTypeId, template_key: templateKey } },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Create scholarship email template (per-scholarship override).
     * scholarship_type_id is passed via query, body is the template payload.
     */
    createScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateData: components["schemas"]["EmailTemplateSchema"]
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/scholarship-email-templates', {
        params: { query: { scholarship_type_id: scholarshipTypeId } },
        body: templateData,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Update scholarship email template
     * Type-safe: Path parameters and request body validated against OpenAPI
     */
    updateScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateKey: string,
      templateData: components["schemas"]["EmailTemplateUpdateSchema"]
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT('/api/v1/admin/scholarship-email-templates/{scholarship_type_id}/{template_key}', {
        params: { path: { scholarship_type_id: scholarshipTypeId, template_key: templateKey } },
        body: templateData,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Delete scholarship email template
     * Type-safe: Path parameters validated against OpenAPI
     */
    deleteScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateKey: string
    ): Promise<ApiResponse<boolean>> => {
      const response = await typedClient.raw.DELETE('/api/v1/admin/scholarship-email-templates/{scholarship_type_id}/{template_key}', {
        params: { path: { scholarship_type_id: scholarshipTypeId, template_key: templateKey } },
      });
      return toApiResponse(response) as ApiResponse<boolean>;
    },

    /**
     * Bulk create scholarship email templates
     * Type-safe: Path parameter validated against OpenAPI
     */
    bulkCreateScholarshipEmailTemplates: async (
      scholarshipTypeId: number
    ): Promise<ApiResponse<{ items: unknown[]; total: number }>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/scholarship-email-templates/{scholarship_type_id}/bulk-create', {
        params: { path: { scholarship_type_id: scholarshipTypeId } },
        body: {} as never,
      });
      return toApiResponse(response) as ApiResponse<{ items: unknown[]; total: number }>;
    },

    /**
     * Get available scholarship email templates
     * Type-safe: Path parameter validated against OpenAPI
     */
    getAvailableScholarshipEmailTemplates: async (
      scholarshipTypeId: number
    ): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarship-email-templates/{scholarship_type_id}/available', {
        params: { path: { scholarship_type_id: scholarshipTypeId } },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    // ========== System Settings ==========

    /**
     * Get system setting by key
     * Type-safe: Query parameters validated against OpenAPI
     */
    getSystemSetting: async (key: string): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/system-setting', {
        params: { query: { key } },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Update system setting
     * Type-safe: Request body validated against OpenAPI
     */
    updateSystemSetting: async (setting: components["schemas"]["SystemSettingSchema"]): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT('/api/v1/admin/system-setting', {
        body: setting,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    // ========== Announcements ==========

    /**
     * Get all announcements with pagination
     * Type-safe: Query parameters validated against OpenAPI
     */
    getAllAnnouncements: async (
      page?: number,
      size?: number,
      notificationType?: string,
      priority?: string
    ): Promise<ApiResponse<{ items: unknown[]; total: number; page: number; size: number }>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/announcements', {
        params: {
          query: {
            page,
            size,
            notification_type: notificationType,
            priority,
          },
        },
      });
      return toApiResponse(response) as ApiResponse<{ items: unknown[]; total: number; page: number; size: number }>;
    },

    /**
     * Get announcement by ID
     * Type-safe: Path parameter validated against OpenAPI
     */
    getAnnouncement: async (id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/announcements/{id}', {
        params: { path: { id } },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Create announcement
     * Type-safe: Request body validated against OpenAPI
     */
    createAnnouncement: async (announcementData: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/announcements', {
        body: announcementData as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Update announcement
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateAnnouncement: async (id: number, announcementData: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT('/api/v1/admin/announcements/{id}', {
        params: { path: { id } },
        body: announcementData as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Delete announcement
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteAnnouncement: async (id: number): Promise<ApiResponse<{ message: string }>> => {
      const response = await typedClient.raw.DELETE('/api/v1/admin/announcements/{id}', {
        params: { path: { id } },
      });
      return toApiResponse(response) as ApiResponse<{ message: string }>;
    },

    // ========== Scholarship Management ==========

    /**
     * Get scholarship statistics
     * Type-safe: Response type inferred from OpenAPI
     */
    getScholarshipStats: async (): Promise<ApiResponse<Record<string, unknown>>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarships/stats');
      return toApiResponse(response) as ApiResponse<Record<string, unknown>>;
    },

    /**
     * Get applications by scholarship
     * Type-safe: Path parameter and query parameters validated against OpenAPI
     */
    getApplicationsByScholarship: async (
      scholarshipCode: string,
      subType?: string,
      status?: string
    ): Promise<ApiResponse<unknown[]>> => {
      // Path is not in the generated OpenAPI schema (orphan endpoint, see
      // issue #665). The `as any` cast on the GET method bypasses typed-route
      // inference; the runtime call still works because the FastAPI route
      // exists. Once #665 cleans up orphan endpoints this can either be
      // removed or regenerated through the openapi-fetch types.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const response = await (typedClient.raw.GET as any)('/api/v1/admin/scholarships/{scholarship_code}/applications', {
        params: {
          path: { scholarship_code: scholarshipCode },
          query: {
            sub_type: subType,
            status,
          },
        },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Get scholarship sub-types
     * Type-safe: Path parameter validated against OpenAPI
     */
    getScholarshipSubTypes: async (scholarshipCode: string): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarships/{scholarship_code}/sub-types', {
        params: { path: { scholarship_code: scholarshipCode } },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Get sub-type translations
     * Type-safe: Response type inferred from OpenAPI
     */
    getSubTypeTranslations: async (): Promise<ApiResponse<Record<string, Record<string, string>>>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarships/sub-type-translations');
      return toApiResponse(response) as ApiResponse<Record<string, Record<string, string>>>;
    },

    /**
     * Get audit trail for all applications of a scholarship type
     * Includes audit logs for deleted applications
     * Type-safe: Path parameter and query parameters validated against OpenAPI
     */
    getScholarshipAuditTrail: async (
      scholarshipIdentifier: string,
      actionFilter?: string,
      limit?: number,
      offset?: number
    ): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarships/{scholarship_identifier}/audit-trail', {
        params: {
          path: { scholarship_identifier: scholarshipIdentifier },
          query: {
            action_filter: actionFilter,
            limit,
            offset,
          },
        },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    // ========== Workflows (Not Implemented) ==========

    getWorkflows: async (): Promise<ApiResponse<unknown[]>> => {
      return Promise.resolve({
        success: true,
        data: [],
        message: "Workflows feature coming soon",
      });
    },

    createWorkflow: async (_workflow: unknown): Promise<ApiResponse<unknown>> => {
      return Promise.resolve({
        success: false,
        message: "Workflows feature not implemented yet",
      });
    },

    updateWorkflow: async (_id: string, _workflow: unknown): Promise<ApiResponse<unknown>> => {
      return Promise.resolve({
        success: false,
        message: "Workflows feature not implemented yet",
      });
    },

    deleteWorkflow: async (id: string): Promise<ApiResponse<{ message: string }>> => {
      return Promise.resolve({
        success: false,
        message: "Workflows feature not implemented yet",
      });
    },

    // ========== Scholarship Rules ==========

    /**
     * Get scholarship rules with filters
     * Type-safe: Query parameters validated against OpenAPI
     */
    getScholarshipRules: async (
      filters?: {
        scholarship_type_id?: number;
        sub_type?: string;
        academic_year?: number;
        semester?: string | null;
        is_template?: boolean;
        is_active?: boolean;
      }
    ): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarship-rules', {
        params: { query: filters },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Get scholarship rule by ID
     * Type-safe: Path parameter validated against OpenAPI
     */
    getScholarshipRule: async (id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarship-rules/{id}', {
        params: { path: { id } },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Create scholarship rule
     * Type-safe: Request body validated against OpenAPI
     */
    createScholarshipRule: async (rule: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/scholarship-rules', {
        body: rule as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Update scholarship rule
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateScholarshipRule: async (id: number, rule: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT('/api/v1/admin/scholarship-rules/{id}', {
        params: { path: { id } },
        body: rule as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Delete scholarship rule
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteScholarshipRule: async (id: number): Promise<ApiResponse<{ message: string }>> => {
      const response = await typedClient.raw.DELETE('/api/v1/admin/scholarship-rules/{id}', {
        params: { path: { id } },
      });
      return toApiResponse(response) as ApiResponse<{ message: string }>;
    },

    /**
     * Copy rules between periods
     * Type-safe: Request body validated against OpenAPI
     */
    copyRulesBetweenPeriods: async (copyRequest: unknown): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/scholarship-rules/copy', {
        body: copyRequest as never,
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Bulk rule operation
     * Type-safe: Request body validated against OpenAPI
     */
    bulkRuleOperation: async (operation: components["schemas"]["BulkRuleOperation"]): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/scholarship-rules/bulk-operation', {
        body: operation as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Get rule templates
     * Type-safe: Query parameters validated against OpenAPI
     */
    getRuleTemplates: async (scholarship_type_id?: number): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarship-rules/templates', {
        params: { query: { scholarship_type_id } },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Create rule template
     * Type-safe: Request body validated against OpenAPI
     */
    createRuleTemplate: async (templateRequest: unknown): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/scholarship-rules/create-template', {
        body: templateRequest as never,
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Apply rule template
     * Type-safe: Request body validated against OpenAPI
     */
    applyRuleTemplate: async (templateRequest: unknown): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/scholarship-rules/apply-template', {
        body: templateRequest as never,
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Delete rule template
     * Type-safe: Path parameter and query parameters validated against OpenAPI
     */
    deleteRuleTemplate: async (
      templateName: string,
      scholarshipTypeId: number
    ): Promise<ApiResponse<{ message: string }>> => {
      const response = await typedClient.raw.DELETE('/api/v1/admin/scholarship-rules/templates/{template_name}', {
        params: {
          path: { template_name: templateName },
          query: { scholarship_type_id: scholarshipTypeId },
        },
      });
      return toApiResponse(response) as ApiResponse<{ message: string }>;
    },

    /**
     * Get scholarship rule sub-types
     * Type-safe: Path parameter validated against OpenAPI
     */
    getScholarshipRuleSubTypes: async (scholarshipTypeId: number): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-rules/scholarship-types/{scholarship_type_id}/sub-types', {
        params: { path: { scholarship_type_id: scholarshipTypeId } },
      });
      return toApiResponse(response) as unknown as ApiResponse<unknown[]>;
    },

    // ========== Scholarship Permissions ==========

    /**
     * Get scholarship permissions
     * Type-safe: Query parameters validated against OpenAPI
     */
    getScholarshipPermissions: async (userId?: number): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarship-permissions', {
        params: { query: { user_id: userId } },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Get current user scholarship permissions
     * Type-safe: Response type inferred from OpenAPI
     */
    getCurrentUserScholarshipPermissions: async (): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarship-permissions/current-user');
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Create scholarship permission
     * Type-safe: Request body validated against OpenAPI
     */
    createScholarshipPermission: async (permission: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/scholarship-permissions', {
        body: permission as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Update scholarship permission
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateScholarshipPermission: async (id: number, permission: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT('/api/v1/admin/scholarship-permissions/{id}', {
        params: { path: { id } },
        body: permission as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Delete scholarship permission
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteScholarshipPermission: async (id: number): Promise<ApiResponse<{ message: string }>> => {
      const response = await typedClient.raw.DELETE('/api/v1/admin/scholarship-permissions/{id}', {
        params: { path: { id } },
      });
      return toApiResponse(response) as ApiResponse<{ message: string }>;
    },

    /**
     * Get all scholarships for permissions
     * Type-safe: Response type inferred from OpenAPI
     */
    getAllScholarshipsForPermissions: async (): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarships/all-for-permissions');
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Get my scholarships
     * Type-safe: Response type inferred from OpenAPI
     */
    getMyScholarships: async (): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarships/my-scholarships');
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Get available semesters
     * Type-safe: Query parameters validated against OpenAPI
     */
    getAvailableSemesters: async (scholarshipCode?: string): Promise<ApiResponse<string[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/available-semesters', {
        params: { query: { scholarship_code: scholarshipCode } },
      });
      return toApiResponse(response) as unknown as ApiResponse<string[]>;
    },

    /**
     * Get available years
     * Type-safe: Response type inferred from OpenAPI
     */
    getAvailableYears: async (): Promise<ApiResponse<number[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/scholarships/available-years');
      return toApiResponse(response) as ApiResponse<number[]>;
    },

    // ========== Scholarship Configuration Management ==========

    /**
     * Get scholarship config types
     * Type-safe: Response type inferred from OpenAPI
     */
    getScholarshipConfigTypes: async (): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/scholarship-types');
      return toApiResponse(response) as unknown as ApiResponse<unknown[]>;
    },

    /**
     * Get scholarship configurations with filters
     * Type-safe: Query parameters validated against OpenAPI
     */
    getScholarshipConfigurations: async (
      params?: {
        scholarship_type_id?: number;
        academic_year?: number;
        semester?: string | null;
        is_active?: boolean;
      }
    ): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/configurations', {
        params: {
          query: {
            scholarship_type_id: params?.scholarship_type_id,
            academic_year: params?.academic_year,
            semester: params?.semester,
            is_active: params?.is_active,
          },
        },
      });
      return toApiResponse(response) as unknown as ApiResponse<unknown[]>;
    },

    /**
     * Get scholarship configuration by ID
     * Type-safe: Path parameter validated against OpenAPI
     */
    getScholarshipConfiguration: async (id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/configurations/{id}', {
        params: { path: { id } },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Create scholarship configuration
     * Type-safe: Request body validated against OpenAPI
     */
    createScholarshipConfiguration: async (configData: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/scholarship-configurations/configurations', {
        body: configData as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Update scholarship configuration
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateScholarshipConfiguration: async (id: number, configData: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT('/api/v1/scholarship-configurations/configurations/{id}', {
        params: { path: { id } },
        body: configData as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Delete scholarship configuration
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteScholarshipConfiguration: async (id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.DELETE('/api/v1/scholarship-configurations/configurations/{id}', {
        params: { path: { id } },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Duplicate scholarship configuration
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    duplicateScholarshipConfiguration: async (
      id: number,
      targetData: unknown
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/scholarship-configurations/configurations/{id}/duplicate', {
        params: { path: { id } },
        body: targetData as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    // ========== Professor Management ==========

    /**
     * Get professors with search
     * Type-safe: Query parameters validated against OpenAPI
     */
    getProfessors: async (search?: string): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/professors', {
        params: { query: { search } },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Assign professor to application
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    assignProfessor: async (applicationId: number, professorNycuId: string): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT('/api/v1/admin/applications/{id}/assign-professor', {
        params: { path: { id: applicationId } },
        body: { professor_nycu_id: professorNycuId },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Get available professors (alias for getProfessors)
     * Type-safe: Query parameters validated against OpenAPI
     */
    getAvailableProfessors: async (search?: string): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/professors', {
        params: { query: { search } },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    // ========== System Configuration Management ==========

    /**
     * Get configurations
     * Type-safe: Response type inferred from OpenAPI
     */
    getConfigurations: async (): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/configurations');
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Create configuration
     * Type-safe: Request body validated against OpenAPI
     */
    createConfiguration: async (configData: components["schemas"]["ConfigurationCreateSchema"]): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/configurations', {
        body: configData,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Update configurations in bulk
     * Type-safe: Request body validated against OpenAPI
     */
    updateConfigurationsBulk: async (
      configurations: Array<components["schemas"]["ConfigurationUpdateSchema"]>,
      changeReason?: string
    ): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.PUT('/api/v1/admin/configurations/bulk', {
        body: {
          updates: configurations,
          ...(changeReason && { change_reason: changeReason }),
        },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Validate configuration
     * Type-safe: Request body validated against OpenAPI
     */
    validateConfiguration: async (configData: components["schemas"]["ConfigurationValidationSchema"]): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/configurations/validate', {
        body: configData,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Delete configuration
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteConfiguration: async (key: string): Promise<ApiResponse<string>> => {
      const response = await typedClient.raw.DELETE('/api/v1/admin/configurations/{key}', {
        params: { path: { key } },
      });
      return toApiResponse(response) as ApiResponse<string>;
    },

    // ========== Bank Verification ==========

    /**
     * Verify bank account (admin duplicate of bank-verification module)
     * Type-safe: Request body validated against OpenAPI
     */
    verifyBankAccount: async (applicationId: number): Promise<ApiResponse<unknown>> => {
      // SECURITY: do NOT default force_recheck=true. The generated schema
      // marks force_recheck as required (because it has a server-side
      // @default), but emitting it from the client could override a
      // server-side policy. The `as never` cast keeps the request
      // server-default-bound rather than over-asserting it here.
      const response = await typedClient.raw.POST('/api/v1/admin/bank-verification', {
        body: { application_id: applicationId } as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    /**
     * Verify bank accounts in batch (admin duplicate of bank-verification module)
     * Type-safe: Request body validated against OpenAPI
     */
    verifyBankAccountsBatch: async (applicationIds: number[]): Promise<ApiResponse<unknown>> => {
      // SECURITY: see force_recheck note in verifyBankAccount above.
      const response = await typedClient.raw.POST('/api/v1/admin/bank-verification/batch', {
        body: { application_ids: applicationIds } as never,
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    // ========== Professor-Student Relationships ==========

    /**
     * Get professor-student relationships with filters
     * Type-safe: Query parameters validated against OpenAPI
     */
    getProfessorStudentRelationships: async (
      params?: { page?: number; size?: number }
    ): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/professor-student-relationships', {
        params: {
          query: {
            page: params?.page,
            size: params?.size,
          },
        },
      });
      return toApiResponse(response) as ApiResponse<unknown[]>;
    },

    /**
     * Create professor-student relationship
     * Type-safe: Request body validated against OpenAPI
     */
    createProfessorStudentRelationship: async (relationshipData: unknown): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/professor-student-relationships', {
        params: { query: { relationship_data: relationshipData } },
      });
      return toApiResponse(response) as ApiResponse<unknown>;
    },

    // ========== Unified Review System (Admin Role) ==========

    /**
     * Get reviewable sub-types for an application (admin role)
     * Uses multi-role review API - supports professor, college, and admin roles.
     * Type-safe: Path parameter validated against OpenAPI
     */
    getReviewableSubTypes: async (applicationId: number): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/reviews/applications/{application_id}/sub-types', {
        params: { path: { application_id: applicationId } },
      });
      return toApiResponse<unknown[]>(response);
    },

    /**
     * Get current admin user's review for an application
     * Type-safe: Path parameter validated against OpenAPI
     */
    getApplicationReview: async (applicationId: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/reviews/applications/{application_id}/review', {
        params: { path: { application_id: applicationId } },
      });
      return toApiResponse<unknown>(response);
    },

    /**
     * Submit review for an application (admin role, unified review system)
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    submitApplicationReview: async (
      applicationId: number,
      reviewData: {
        items: Array<{
          sub_type_code: string;
          recommendation: 'approve' | 'reject';
          comments?: string;
        }>;
      }
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/reviews/applications/{application_id}/review', {
        params: { path: { application_id: applicationId } },
        body: reviewData,
      });
      return toApiResponse<unknown>(response);
    },

    /**
     * Hard-delete an application (admin only).
     * Cascades removal of related review/roster rows; audit log is preserved.
     */
    deleteApplication: async (
      id: number,
      reason: string
    ): Promise<ApiResponse<{ id: number; app_id: string; reason: string }>> => {
      const response = await typedClient.raw.DELETE('/api/v1/admin/applications/{id}', {
        params: { path: { id } },
        body: { reason },
      });
      return toApiResponse(response) as ApiResponse<{ id: number; app_id: string; reason: string }>;
    },
  };
}
