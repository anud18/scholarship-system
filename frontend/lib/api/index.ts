/**
 * Unified API Client Export
 *
 * This file provides a modular, maintainable API structure while maintaining
 * backward compatibility with the original api.ts interface.
 *
 * Usage:
 *   import { api } from '@/lib/api';
 *   // OR
 *   import { api } from '@/lib/api/index';
 *
 *   const response = await api.auth.login(username, password);
 */

import { ApiClient } from './client';
import { typedClient } from './typed-client';
import { createAuthApi } from './modules/auth';
import { createUsersApi } from './modules/users';
import { createScholarshipsApi } from './modules/scholarships';
import { createApplicationsApi } from './modules/applications';
import { createNotificationsApi } from './modules/notifications';
import { createQuotaApi } from './modules/quota';
import { createProfessorApi } from './modules/professor';
import { createCollegeApi } from './modules/college';
import { createWhitelistApi } from './modules/whitelist';
import { createSystemSettingsApi } from './modules/system-settings';
import { createBankVerificationApi } from './modules/bank-verification';
import { createProfessorStudentApi } from './modules/professor-student';
import { createEmailAutomationApi } from './modules/email-automation';
import { createBatchImportApi } from './modules/batch-import';
import { createReferenceDataApi } from './modules/reference-data';
import { createApplicationFieldsApi } from './modules/application-fields';
import { createUserProfilesApi } from './modules/user-profiles';
import { createEmailManagementApi } from './modules/email-management';
import { createAdminApi } from './modules/admin';
import { createDocumentRequestsApi } from './modules/document-requests';
import { createPaymentRostersApi } from './modules/payment-rosters';
import { createStudentsApi } from './modules/students';
// import { createReviewApi } from './modules/reviews'; // Not used - professor reviews use professor endpoints with adapter

// Re-export ALL types from modular types file
export type {
  // Core types
  ApiResponse,
  PaginatedResponse,
  User,
  // Student type is now exported from modules/students.ts (see below)
  StudentInfoResponse,
  Application,
  ApplicationStatus,
  ApplicationFile,
  ScholarshipType,
  WhitelistStudentInfo,
  WhitelistResponse,
  // Scholarship types
  ScholarshipConfiguration,
  ScholarshipRule,
  ScholarshipStats,
  SubTypeStats,
  SubTypeOption,
  ScholarshipPermission,
  ScholarshipPermissionCreate,
  ScholarshipConfigurationFormData,
  ScholarshipFormConfig,
  // Application types
  ApplicationCreate,
  ApplicationField,
  ApplicationFieldCreate,
  ApplicationFieldUpdate,
  ApplicationDocument,
  ApplicationDocumentCreate,
  ApplicationDocumentUpdate,
  FormConfigSaveRequest,
  HistoricalApplication,
  HistoricalApplicationFilters,
  // System types
  DashboardStats,
  SystemSetting,
  SystemConfiguration,
  SystemConfigurationCreate,
  SystemConfigurationUpdate,
  SystemConfigurationValidation,
  ConfigurationValidationResult,
  SystemStats,
  Workflow,
  // Email types
  EmailTemplate,
  RecipientOption,
  // Notification types
  AnnouncementCreate,
  AnnouncementUpdate,
  NotificationResponse,
  // User types
  UserListResponse,
  UserResponse,
  UserCreate,
  UserUpdate,
  UserStats,
  UserProfile,
  CompleteUserProfile,
  // Bank verification types
  BankVerificationResult,
  BankVerificationBatchResult,
  // Professor-Student types
  ProfessorStudentRelationship,
  ProfessorStudentRelationshipCreate,
  ProfessorStudentRelationshipUpdate,
  // Whitelist types
  WhitelistBatchAddRequest,
  WhitelistBatchRemoveRequest,
  WhitelistImportResult,
  WhitelistToggleRequest,
} from './types';

// Re-export Students module types
export type {
  Student,
  StudentStats,
  StudentSISBasicInfo,
  StudentSISTermData,
  StudentSISData,
} from './modules/students';

// Re-export quota helper functions
export {
  calculateTotalQuota,
  calculateUsagePercentage,
  getQuotaStatusColor,
} from './modules/quota';

/**
 * Extended ApiClient with all API modules (Lazy-loaded)
 *
 * This class uses lazy loading to reduce initial bundle size.
 * Each module is only loaded when first accessed.
 */
class ExtendedApiClient extends ApiClient {
  // Private properties for lazy initialization
  private _auth?: ReturnType<typeof createAuthApi>;
  private _users?: ReturnType<typeof createUsersApi>;
  private _scholarships?: ReturnType<typeof createScholarshipsApi>;
  private _applications?: ReturnType<typeof createApplicationsApi>;
  private _notifications?: ReturnType<typeof createNotificationsApi>;
  private _quota?: ReturnType<typeof createQuotaApi>;
  private _professor?: ReturnType<typeof createProfessorApi>;
  private _college?: ReturnType<typeof createCollegeApi>;
  private _whitelist?: ReturnType<typeof createWhitelistApi>;
  private _systemSettings?: ReturnType<typeof createSystemSettingsApi>;
  private _bankVerification?: ReturnType<typeof createBankVerificationApi>;
  private _professorStudent?: ReturnType<typeof createProfessorStudentApi>;
  private _emailAutomation?: ReturnType<typeof createEmailAutomationApi>;
  private _batchImport?: ReturnType<typeof createBatchImportApi>;
  private _referenceData?: ReturnType<typeof createReferenceDataApi>;
  private _applicationFields?: ReturnType<typeof createApplicationFieldsApi>;
  private _userProfiles?: ReturnType<typeof createUserProfilesApi>;
  private _emailManagement?: ReturnType<typeof createEmailManagementApi>;
  private _admin?: ReturnType<typeof createAdminApi>;
  private _documentRequests?: ReturnType<typeof createDocumentRequestsApi>;
  private _paymentRosters?: ReturnType<typeof createPaymentRostersApi>;
  private _students?: ReturnType<typeof createStudentsApi>;

  // Lazy-loaded getters
  get auth(): ReturnType<typeof createAuthApi> {
    if (!this._auth) this._auth = createAuthApi();
    return this._auth;
  }

  get users(): ReturnType<typeof createUsersApi> {
    if (!this._users) this._users = createUsersApi();
    return this._users;
  }

  get scholarships(): ReturnType<typeof createScholarshipsApi> {
    if (!this._scholarships) this._scholarships = createScholarshipsApi();
    return this._scholarships;
  }

  get applications(): ReturnType<typeof createApplicationsApi> {
    if (!this._applications) this._applications = createApplicationsApi();
    return this._applications;
  }

  get notifications(): ReturnType<typeof createNotificationsApi> {
    if (!this._notifications) this._notifications = createNotificationsApi();
    return this._notifications;
  }

  get quota(): ReturnType<typeof createQuotaApi> {
    if (!this._quota) this._quota = createQuotaApi();
    return this._quota;
  }

  get professor(): ReturnType<typeof createProfessorApi> {
    if (!this._professor) this._professor = createProfessorApi();
    return this._professor;
  }

  get college(): ReturnType<typeof createCollegeApi> {
    if (!this._college) this._college = createCollegeApi();
    return this._college;
  }

  get whitelist(): ReturnType<typeof createWhitelistApi> {
    if (!this._whitelist) this._whitelist = createWhitelistApi();
    return this._whitelist;
  }

  get systemSettings(): ReturnType<typeof createSystemSettingsApi> {
    if (!this._systemSettings) this._systemSettings = createSystemSettingsApi();
    return this._systemSettings;
  }

  get bankVerification(): ReturnType<typeof createBankVerificationApi> {
    if (!this._bankVerification) this._bankVerification = createBankVerificationApi();
    return this._bankVerification;
  }

  get professorStudent(): ReturnType<typeof createProfessorStudentApi> {
    if (!this._professorStudent) this._professorStudent = createProfessorStudentApi();
    return this._professorStudent;
  }

  get emailAutomation(): ReturnType<typeof createEmailAutomationApi> {
    if (!this._emailAutomation) this._emailAutomation = createEmailAutomationApi();
    return this._emailAutomation;
  }

  get batchImport(): ReturnType<typeof createBatchImportApi> {
    if (!this._batchImport) this._batchImport = createBatchImportApi();
    return this._batchImport;
  }

  get referenceData(): ReturnType<typeof createReferenceDataApi> {
    if (!this._referenceData) this._referenceData = createReferenceDataApi();
    return this._referenceData;
  }

  get applicationFields(): ReturnType<typeof createApplicationFieldsApi> {
    if (!this._applicationFields) this._applicationFields = createApplicationFieldsApi();
    return this._applicationFields;
  }

  get userProfiles(): ReturnType<typeof createUserProfilesApi> {
    if (!this._userProfiles) this._userProfiles = createUserProfilesApi();
    return this._userProfiles;
  }

  get emailManagement(): ReturnType<typeof createEmailManagementApi> {
    if (!this._emailManagement) this._emailManagement = createEmailManagementApi();
    return this._emailManagement;
  }

  get admin(): ReturnType<typeof createAdminApi> {
    if (!this._admin) this._admin = createAdminApi();
    return this._admin;
  }

  get documentRequests(): ReturnType<typeof createDocumentRequestsApi> {
    if (!this._documentRequests) this._documentRequests = createDocumentRequestsApi();
    return this._documentRequests;
  }

  get paymentRosters(): ReturnType<typeof createPaymentRostersApi> {
    if (!this._paymentRosters) this._paymentRosters = createPaymentRostersApi();
    return this._paymentRosters;
  }

  get students(): ReturnType<typeof createStudentsApi> {
    if (!this._students) this._students = createStudentsApi();
    return this._students;
  }

  // Backward compatibility alias
  get system(): ReturnType<typeof createSystemSettingsApi> {
    return this.systemSettings;
  }

  constructor() {
    super();
  }

  /**
   * Override setToken to synchronize with typedClient
   * This ensures modules using typedClient also have the token
   */
  setToken(token: string): void {
    super.setToken(token);
    typedClient.setToken(token);
  }

  /**
   * Override clearToken to synchronize with typedClient
   */
  clearToken(): void {
    super.clearToken();
    typedClient.clearToken();
  }

  /**
   * Override getToken to delegate to typedClient
   * This ensures we always get the current state, even if typedClient clears the token
   */
  getToken(): string | null {
    return typedClient.getToken();
  }

  /**
   * Override hasToken to delegate to typedClient
   */
  hasToken(): boolean {
    return typedClient.hasToken();
  }
}

/**
 * Singleton API client instance
 *
 * This provides a consistent API surface across the application while
 * allowing for modular organization of API methods internally.
 */
export const apiClient = new ExtendedApiClient();

/**
 * Default export for convenience
 */
export default apiClient;

/**
 * Alias for backward compatibility
 *
 * This maintains compatibility with existing code that uses:
 *   import { api } from '@/lib/api';
 */
export const api = apiClient;

/**
 * Export the base ApiClient class for advanced use cases
 *
 * This allows creating custom API clients if needed, though
 * most code should use the singleton instance above.
 */
export { ApiClient };
