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
    this.auth = createAuthApi(); // Now using typed client internally
    this.users = createUsersApi(); // Now using typed client internally
    this.scholarships = createScholarshipsApi(); // Now using typed client internally
    this.applications = createApplicationsApi(); // Now using typed client internally
    this.notifications = createNotificationsApi(); // Now using typed client internally
    this.quota = createQuotaApi(); // Now using typed client internally
    this.professor = createProfessorApi(); // Now using typed client internally
    this.college = createCollegeApi(); // Now using typed client internally
    this.whitelist = createWhitelistApi(); // Now using typed client internally
    this.systemSettings = createSystemSettingsApi(); // Now using typed client internally
    this.bankVerification = createBankVerificationApi(); // Now using typed client internally
    this.professorStudent = createProfessorStudentApi(); // Now using typed client internally
    this.emailAutomation = createEmailAutomationApi(); // Now using typed client internally
    this.batchImport = createBatchImportApi(); // Now using typed client internally
    this.referenceData = createReferenceDataApi(); // Now using typed client internally
    this.applicationFields = createApplicationFieldsApi(); // Now using typed client internally
    this.userProfiles = createUserProfilesApi(); // Now using typed client internally
    this.emailManagement = createEmailManagementApi(); // Now using typed client internally
    this.admin = createAdminApi(); // Now using typed client internally

    // Initialize backward compatibility alias
    this.system = this.systemSettings;
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
