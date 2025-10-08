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

// Re-export types from main api.ts for now
// TODO: Move these to a dedicated types.ts file
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
  Notification,
  PaginatedResponse,
} from '../api';

/**
 * Extended ApiClient with all API modules
 */
class ExtendedApiClient extends ApiClient {
  public auth: ReturnType<typeof createAuthApi>;
  public users: ReturnType<typeof createUsersApi>;
  public scholarships: ReturnType<typeof createScholarshipsApi>;

  // TODO: Add other modules as they are migrated
  // public applications: ReturnType<typeof createApplicationsApi>;
  // public notifications: ReturnType<typeof createNotificationsApi>;
  // public admin: ReturnType<typeof createAdminApi>;

  constructor() {
    super();

    // Initialize modules
    this.auth = createAuthApi(this);
    this.users = createUsersApi(this);
    this.scholarships = createScholarshipsApi(this);

    // TODO: Initialize other modules as they are created
    // this.applications = createApplicationsApi(this);
    // this.notifications = createNotificationsApi(this);
    // this.admin = createAdminApi(this);
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
