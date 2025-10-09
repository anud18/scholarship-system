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

// Re-export ALL types from legacy api.ts for backward compatibility
// TODO: Move these to a dedicated types.ts file in the modular structure
export type {
  ApiResponse,
  User,
  Student,
  StudentInfoResponse,
  Application,
  ApplicationStatus,
  ApplicationFile,
  ScholarshipType,
  ScholarshipConfiguration,
  ScholarshipRule,
  PaginatedResponse,
  ApplicationCreate,
  DashboardStats,
  RecipientOption,
  EmailTemplate,
  SystemSetting,
  SystemConfiguration,
  SystemConfigurationCreate,
  SystemConfigurationUpdate,
  SystemConfigurationValidation,
  ConfigurationValidationResult,
  BankVerificationResult,
  BankVerificationBatchResult,
  ProfessorStudentRelationship,
  ProfessorStudentRelationshipCreate,
  ProfessorStudentRelationshipUpdate,
  AnnouncementCreate,
  AnnouncementUpdate,
  NotificationResponse,
  SubTypeOption,
  UserListResponse,
  UserResponse,
  UserCreate,
  UserUpdate,
  UserStats,
  ApplicationField,
  ApplicationFieldCreate,
  ApplicationFieldUpdate,
  ApplicationDocument,
  HistoricalApplication,
  HistoricalApplicationFilters,
  ApplicationDocumentCreate,
  ApplicationDocumentUpdate,
  ScholarshipFormConfig,
  FormConfigSaveRequest,
  ScholarshipStats,
  SubTypeStats,
  Workflow,
  SystemStats,
  ScholarshipPermission,
  ScholarshipPermissionCreate,
  WhitelistStudentInfo,
  WhitelistResponse,
  WhitelistBatchAddRequest,
  WhitelistBatchRemoveRequest,
  WhitelistImportResult,
  WhitelistToggleRequest,
  ScholarshipConfigurationFormData,
  UserProfile,
  CompleteUserProfile,
} from '../api.legacy';

// Re-export quota helper functions
export {
  calculateTotalQuota,
  calculateUsagePercentage,
  getQuotaStatusColor,
} from './modules/quota';

/**
 * Extended ApiClient with all API modules
 */
class ExtendedApiClient extends ApiClient {
  public auth: ReturnType<typeof createAuthApi>;
  public users: ReturnType<typeof createUsersApi>;
  public scholarships: ReturnType<typeof createScholarshipsApi>;
  public applications: ReturnType<typeof createApplicationsApi>;
  public notifications: ReturnType<typeof createNotificationsApi>;
  public quota: ReturnType<typeof createQuotaApi>;
  public professor: ReturnType<typeof createProfessorApi>;
  public college: ReturnType<typeof createCollegeApi>;
  public whitelist: ReturnType<typeof createWhitelistApi>;
  public systemSettings: ReturnType<typeof createSystemSettingsApi>;
  public bankVerification: ReturnType<typeof createBankVerificationApi>;
  public professorStudent: ReturnType<typeof createProfessorStudentApi>;
  public emailAutomation: ReturnType<typeof createEmailAutomationApi>;
  public batchImport: ReturnType<typeof createBatchImportApi>;
  public referenceData: ReturnType<typeof createReferenceDataApi>;
  public applicationFields: ReturnType<typeof createApplicationFieldsApi>;
  public userProfiles: ReturnType<typeof createUserProfilesApi>;
  public emailManagement: ReturnType<typeof createEmailManagementApi>;
  public admin: ReturnType<typeof createAdminApi>;

  // Backward compatibility alias
  public system: ReturnType<typeof createSystemSettingsApi>;

  constructor() {
    super();

    // Initialize modules
    this.auth = createAuthApi(this);
    this.users = createUsersApi(this);
    this.scholarships = createScholarshipsApi(this);
    this.applications = createApplicationsApi(this);
    this.notifications = createNotificationsApi(this);
    this.quota = createQuotaApi(this);
    this.professor = createProfessorApi(this);
    this.college = createCollegeApi(this);
    this.whitelist = createWhitelistApi(this);
    this.systemSettings = createSystemSettingsApi(this);
    this.bankVerification = createBankVerificationApi(this);
    this.professorStudent = createProfessorStudentApi(this);
    this.emailAutomation = createEmailAutomationApi(this);
    this.batchImport = createBatchImportApi(this);
    this.referenceData = createReferenceDataApi(this);
    this.applicationFields = createApplicationFieldsApi(this);
    this.userProfiles = createUserProfilesApi(this);
    this.emailManagement = createEmailManagementApi(this);
    this.admin = createAdminApi(this);

    // Initialize backward compatibility alias
    this.system = this.systemSettings;
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
