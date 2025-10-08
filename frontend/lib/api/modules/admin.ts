/**
 * Admin API Module
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
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

export function createAdminApi(client: ApiClient) {
  return {
    // ========== Dashboard and Statistics ==========

    getDashboardStats: async (): Promise<ApiResponse<any>> => {
      return client.request("/admin/dashboard/stats");
    },

    getRecentApplications: async (limit?: number): Promise<ApiResponse<any[]>> => {
      const params = limit ? `?limit=${limit}` : "";
      return client.request(`/admin/recent-applications${params}`);
    },

    getSystemAnnouncements: async (limit?: number): Promise<ApiResponse<any[]>> => {
      const params = limit ? `?limit=${limit}` : "";
      return client.request(`/admin/system-announcements${params}`);
    },

    getSystemStats: async (): Promise<ApiResponse<any>> => {
      return client.request("/admin/dashboard/stats");
    },

    // ========== Application Management ==========

    getAllApplications: async (
      page?: number,
      size?: number,
      status?: string
    ): Promise<ApiResponse<{ items: any[]; total: number; page: number; size: number }>> => {
      const params = new URLSearchParams();
      if (page) params.append("page", page.toString());
      if (size) params.append("size", size.toString());
      if (status) params.append("status", status);

      const queryString = params.toString();
      return client.request(`/admin/applications${queryString ? `?${queryString}` : ""}`);
    },

    getHistoricalApplications: async (filters?: any): Promise<ApiResponse<any>> => {
      const params = new URLSearchParams();

      if (filters?.page) params.append("page", filters.page.toString());
      if (filters?.size) params.append("size", filters.size.toString());
      if (filters?.status) params.append("status", filters.status);
      if (filters?.scholarship_type) params.append("scholarship_type", filters.scholarship_type);
      if (filters?.academic_year) params.append("academic_year", filters.academic_year.toString());
      if (filters?.semester) params.append("semester", filters.semester);
      if (filters?.search) params.append("search", filters.search);

      const queryString = params.toString();
      return client.request(`/admin/applications/history${queryString ? `?${queryString}` : ""}`);
    },

    updateApplicationStatus: async (
      applicationId: number,
      status: string,
      reviewNotes?: string
    ): Promise<ApiResponse<any>> => {
      return client.request(`/admin/applications/${applicationId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status, review_notes: reviewNotes }),
      });
    },

    // ========== Email Templates ==========

    getEmailTemplate: async (key: string): Promise<ApiResponse<any>> => {
      return client.request(`/admin/email-template?key=${encodeURIComponent(key)}`);
    },

    updateEmailTemplate: async (template: any): Promise<ApiResponse<any>> => {
      return client.request("/admin/email-template", {
        method: "PUT",
        body: JSON.stringify(template),
      });
    },

    getEmailTemplatesBySendingType: async (sendingType?: string): Promise<ApiResponse<any[]>> => {
      const params = sendingType ? `?sending_type=${encodeURIComponent(sendingType)}` : "";
      return client.request(`/admin/email-templates${params}`);
    },

    // Scholarship Email Templates
    getScholarshipEmailTemplates: async (
      scholarshipTypeId: number
    ): Promise<ApiResponse<{ items: any[]; total: number }>> => {
      return client.request(`/admin/scholarship-email-templates/${scholarshipTypeId}`);
    },

    getScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateKey: string
    ): Promise<ApiResponse<any>> => {
      return client.request(
        `/admin/scholarship-email-templates/${scholarshipTypeId}/${encodeURIComponent(templateKey)}`
      );
    },

    createScholarshipEmailTemplate: async (templateData: any): Promise<ApiResponse<any>> => {
      return client.request("/admin/scholarship-email-templates", {
        method: "POST",
        body: JSON.stringify(templateData),
      });
    },

    updateScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateKey: string,
      templateData: any
    ): Promise<ApiResponse<any>> => {
      return client.request(
        `/admin/scholarship-email-templates/${scholarshipTypeId}/${encodeURIComponent(templateKey)}`,
        {
          method: "PUT",
          body: JSON.stringify(templateData),
        }
      );
    },

    deleteScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateKey: string
    ): Promise<ApiResponse<boolean>> => {
      return client.request(
        `/admin/scholarship-email-templates/${scholarshipTypeId}/${encodeURIComponent(templateKey)}`,
        {
          method: "DELETE",
        }
      );
    },

    bulkCreateScholarshipEmailTemplates: async (
      scholarshipTypeId: number
    ): Promise<ApiResponse<{ items: any[]; total: number }>> => {
      return client.request(`/admin/scholarship-email-templates/${scholarshipTypeId}/bulk-create`, {
        method: "POST",
      });
    },

    getAvailableScholarshipEmailTemplates: async (
      scholarshipTypeId: number
    ): Promise<ApiResponse<any[]>> => {
      return client.request(`/admin/scholarship-email-templates/${scholarshipTypeId}/available`);
    },

    // ========== System Settings ==========

    getSystemSetting: async (key: string): Promise<ApiResponse<any>> => {
      return client.request(`/admin/system-setting?key=${encodeURIComponent(key)}`);
    },

    updateSystemSetting: async (setting: any): Promise<ApiResponse<any>> => {
      return client.request(`/admin/system-setting`, {
        method: "PUT",
        body: JSON.stringify(setting),
      });
    },

    // ========== Announcements ==========

    getAllAnnouncements: async (
      page?: number,
      size?: number,
      notificationType?: string,
      priority?: string
    ): Promise<ApiResponse<{ items: any[]; total: number; page: number; size: number }>> => {
      const params = new URLSearchParams();
      if (page) params.append("page", page.toString());
      if (size) params.append("size", size.toString());
      if (notificationType) params.append("notification_type", notificationType);
      if (priority) params.append("priority", priority);

      const queryString = params.toString();
      return client.request(`/admin/announcements${queryString ? `?${queryString}` : ""}`);
    },

    getAnnouncement: async (id: number): Promise<ApiResponse<any>> => {
      return client.request(`/admin/announcements/${id}`);
    },

    createAnnouncement: async (announcementData: any): Promise<ApiResponse<any>> => {
      return client.request("/admin/announcements", {
        method: "POST",
        body: JSON.stringify(announcementData),
      });
    },

    updateAnnouncement: async (id: number, announcementData: any): Promise<ApiResponse<any>> => {
      return client.request(`/admin/announcements/${id}`, {
        method: "PUT",
        body: JSON.stringify(announcementData),
      });
    },

    deleteAnnouncement: async (id: number): Promise<ApiResponse<{ message: string }>> => {
      return client.request(`/admin/announcements/${id}`, {
        method: "DELETE",
      });
    },

    // ========== Scholarship Management ==========

    getScholarshipStats: async (): Promise<ApiResponse<Record<string, any>>> => {
      return client.request("/admin/scholarships/stats");
    },

    getApplicationsByScholarship: async (
      scholarshipCode: string,
      subType?: string,
      status?: string
    ): Promise<ApiResponse<any[]>> => {
      const params = new URLSearchParams();
      if (subType) params.append("sub_type", subType);
      if (status) params.append("status", status);

      const queryString = params.toString();
      return client.request(
        `/admin/scholarships/${scholarshipCode}/applications${queryString ? `?${queryString}` : ""}`
      );
    },

    getScholarshipSubTypes: async (scholarshipCode: string): Promise<ApiResponse<any[]>> => {
      return client.request(`/admin/scholarships/${scholarshipCode}/sub-types`);
    },

    getSubTypeTranslations: async (): Promise<ApiResponse<Record<string, Record<string, string>>>> => {
      return client.request("/admin/scholarships/sub-type-translations");
    },

    // ========== Workflows (Not Implemented) ==========

    getWorkflows: async (): Promise<ApiResponse<any[]>> => {
      return Promise.resolve({
        success: true,
        data: [],
        message: "Workflows feature coming soon",
      });
    },

    createWorkflow: async (workflow: any): Promise<ApiResponse<any>> => {
      return Promise.resolve({
        success: false,
        message: "Workflows feature not implemented yet",
      });
    },

    updateWorkflow: async (id: string, workflow: any): Promise<ApiResponse<any>> => {
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

    getScholarshipRules: async (filters?: any): Promise<ApiResponse<any[]>> => {
      const queryParams = new URLSearchParams();
      if (filters) {
        Object.entries(filters).forEach(([key, value]) => {
          if (value !== undefined && value !== null) {
            queryParams.append(key, String(value));
          }
        });
      }
      const queryString = queryParams.toString();
      return client.request(`/admin/scholarship-rules${queryString ? `?${queryString}` : ""}`);
    },

    getScholarshipRule: async (id: number): Promise<ApiResponse<any>> => {
      return client.request(`/admin/scholarship-rules/${id}`);
    },

    createScholarshipRule: async (rule: any): Promise<ApiResponse<any>> => {
      return client.request("/admin/scholarship-rules", {
        method: "POST",
        body: JSON.stringify(rule),
      });
    },

    updateScholarshipRule: async (id: number, rule: any): Promise<ApiResponse<any>> => {
      return client.request(`/admin/scholarship-rules/${id}`, {
        method: "PUT",
        body: JSON.stringify(rule),
      });
    },

    deleteScholarshipRule: async (id: number): Promise<ApiResponse<{ message: string }>> => {
      return client.request(`/admin/scholarship-rules/${id}`, {
        method: "DELETE",
      });
    },

    copyRulesBetweenPeriods: async (copyRequest: any): Promise<ApiResponse<any[]>> => {
      return client.request("/admin/scholarship-rules/copy", {
        method: "POST",
        body: JSON.stringify(copyRequest),
      });
    },

    bulkRuleOperation: async (operation: any): Promise<ApiResponse<any>> => {
      return client.request("/admin/scholarship-rules/bulk-operation", {
        method: "POST",
        body: JSON.stringify(operation),
      });
    },

    getRuleTemplates: async (scholarship_type_id?: number): Promise<ApiResponse<any[]>> => {
      const queryParams = scholarship_type_id ? `?scholarship_type_id=${scholarship_type_id}` : "";
      return client.request(`/admin/scholarship-rules/templates${queryParams}`);
    },

    createRuleTemplate: async (templateRequest: any): Promise<ApiResponse<any[]>> => {
      return client.request("/admin/scholarship-rules/create-template", {
        method: "POST",
        body: JSON.stringify(templateRequest),
      });
    },

    applyRuleTemplate: async (templateRequest: any): Promise<ApiResponse<any[]>> => {
      return client.request("/admin/scholarship-rules/apply-template", {
        method: "POST",
        body: JSON.stringify(templateRequest),
      });
    },

    deleteRuleTemplate: async (
      templateName: string,
      scholarshipTypeId: number
    ): Promise<ApiResponse<{ message: string }>> => {
      return client.request(
        `/admin/scholarship-rules/templates/${encodeURIComponent(templateName)}?scholarship_type_id=${scholarshipTypeId}`,
        {
          method: "DELETE",
        }
      );
    },

    getScholarshipRuleSubTypes: async (scholarshipTypeId: number): Promise<ApiResponse<any[]>> => {
      return client.request(`/scholarship-rules/scholarship-types/${scholarshipTypeId}/sub-types`);
    },

    // ========== Scholarship Permissions ==========

    getScholarshipPermissions: async (userId?: number): Promise<ApiResponse<any[]>> => {
      const params = userId ? `?user_id=${userId}` : "";
      return client.request(`/admin/scholarship-permissions${params}`);
    },

    getCurrentUserScholarshipPermissions: async (): Promise<ApiResponse<any[]>> => {
      return client.request("/admin/scholarship-permissions/current-user");
    },

    createScholarshipPermission: async (permission: any): Promise<ApiResponse<any>> => {
      return client.request("/admin/scholarship-permissions", {
        method: "POST",
        body: JSON.stringify(permission),
      });
    },

    updateScholarshipPermission: async (id: number, permission: any): Promise<ApiResponse<any>> => {
      return client.request(`/admin/scholarship-permissions/${id}`, {
        method: "PUT",
        body: JSON.stringify(permission),
      });
    },

    deleteScholarshipPermission: async (id: number): Promise<ApiResponse<{ message: string }>> => {
      return client.request(`/admin/scholarship-permissions/${id}`, {
        method: "DELETE",
      });
    },

    getAllScholarshipsForPermissions: async (): Promise<ApiResponse<any[]>> => {
      return client.request("/admin/scholarships/all-for-permissions");
    },

    getMyScholarships: async (): Promise<ApiResponse<any[]>> => {
      return client.request("/admin/scholarships/my-scholarships");
    },

    getAvailableSemesters: async (scholarshipCode?: string): Promise<ApiResponse<string[]>> => {
      const params = scholarshipCode ? `?scholarship_code=${encodeURIComponent(scholarshipCode)}` : "";
      return client.request(`/scholarship-configurations/available-semesters${params}`);
    },

    getAvailableYears: async (): Promise<ApiResponse<number[]>> => {
      return client.request("/admin/scholarships/available-years");
    },

    // ========== Scholarship Configuration Management ==========

    getScholarshipConfigTypes: async (): Promise<ApiResponse<any[]>> => {
      return client.request("/scholarship-configurations/scholarship-types");
    },

    getScholarshipConfigurations: async (params?: any): Promise<ApiResponse<any[]>> => {
      const queryParams = new URLSearchParams();
      if (params?.scholarship_type_id)
        queryParams.append("scholarship_type_id", params.scholarship_type_id.toString());
      if (params?.academic_year)
        queryParams.append("academic_year", params.academic_year.toString());
      if (params?.semester) queryParams.append("semester", params.semester);
      if (params?.is_active !== undefined)
        queryParams.append("is_active", params.is_active.toString());

      const queryString = queryParams.toString();
      return client.request(
        `/scholarship-configurations/configurations${queryString ? `?${queryString}` : ""}`
      );
    },

    getScholarshipConfiguration: async (id: number): Promise<ApiResponse<any>> => {
      return client.request(`/scholarship-configurations/configurations/${id}`);
    },

    createScholarshipConfiguration: async (configData: any): Promise<ApiResponse<any>> => {
      return client.request("/scholarship-configurations/configurations", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },

    updateScholarshipConfiguration: async (id: number, configData: any): Promise<ApiResponse<any>> => {
      return client.request(`/scholarship-configurations/configurations/${id}`, {
        method: "PUT",
        body: JSON.stringify(configData),
      });
    },

    deleteScholarshipConfiguration: async (id: number): Promise<ApiResponse<any>> => {
      return client.request(`/scholarship-configurations/configurations/${id}`, {
        method: "DELETE",
      });
    },

    duplicateScholarshipConfiguration: async (
      id: number,
      targetData: any
    ): Promise<ApiResponse<any>> => {
      return client.request(`/scholarship-configurations/configurations/${id}/duplicate`, {
        method: "POST",
        body: JSON.stringify(targetData),
      });
    },

    // ========== Professor Management ==========

    getProfessors: async (search?: string): Promise<ApiResponse<any[]>> => {
      const params = search ? { search } : {};
      return client.request("/admin/professors", {
        method: "GET",
        params,
      });
    },

    assignProfessor: async (applicationId: number, professorNycuId: string): Promise<ApiResponse<any>> => {
      return client.request(`/admin/applications/${applicationId}/assign-professor`, {
        method: "PUT",
        body: JSON.stringify({ professor_nycu_id: professorNycuId }),
      });
    },

    getAvailableProfessors: async (search?: string): Promise<ApiResponse<any[]>> => {
      const params = search ? `?search=${encodeURIComponent(search)}` : "";
      return client.request(`/admin/professors${params}`);
    },

    // ========== System Configuration Management ==========

    getConfigurations: async (): Promise<ApiResponse<any[]>> => {
      return client.request("/admin/configurations");
    },

    createConfiguration: async (configData: any): Promise<ApiResponse<any>> => {
      return client.request("/admin/configurations", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },

    updateConfigurationsBulk: async (configurations: any[]): Promise<ApiResponse<any[]>> => {
      return client.request("/admin/configurations/bulk", {
        method: "PUT",
        body: JSON.stringify(configurations),
      });
    },

    validateConfiguration: async (configData: any): Promise<ApiResponse<any>> => {
      return client.request("/admin/configurations/validate", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },

    deleteConfiguration: async (key: string): Promise<ApiResponse<string>> => {
      return client.request(`/admin/configurations/${encodeURIComponent(key)}`, {
        method: "DELETE",
      });
    },

    // ========== Bank Verification ==========

    verifyBankAccount: async (applicationId: number): Promise<ApiResponse<any>> => {
      return client.request("/admin/bank-verification", {
        method: "POST",
        body: JSON.stringify({ application_id: applicationId }),
      });
    },

    verifyBankAccountsBatch: async (applicationIds: number[]): Promise<ApiResponse<any>> => {
      return client.request("/admin/bank-verification/batch", {
        method: "POST",
        body: JSON.stringify({ application_ids: applicationIds }),
      });
    },

    // ========== Professor-Student Relationships ==========

    getProfessorStudentRelationships: async (params?: any): Promise<ApiResponse<any[]>> => {
      const queryParams = new URLSearchParams();
      if (params?.professor_id)
        queryParams.append("professor_id", params.professor_id.toString());
      if (params?.student_id)
        queryParams.append("student_id", params.student_id.toString());
      if (params?.is_active !== undefined)
        queryParams.append("is_active", params.is_active.toString());

      const queryString = queryParams.toString();
      return client.request(
        `/admin/professor-student-relationships${queryString ? `?${queryString}` : ""}`
      );
    },

    createProfessorStudentRelationship: async (relationshipData: any): Promise<ApiResponse<any>> => {
      return client.request("/admin/professor-student-relationships", {
        method: "POST",
        body: JSON.stringify(relationshipData),
      });
    },
  };
}
