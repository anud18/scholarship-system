/**
 * Tests for modular API structure
 *
 * This test verifies that the new modular API maintains the same interface
 * and behavior as the original monolithic api.ts.
 */

import { api, apiClient } from '../index';

// Mock fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock localStorage
const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
};
Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage,
});

describe('Modular API Structure', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLocalStorage.getItem.mockReturnValue(null);
  });

  describe('Exports', () => {
    it('should export api singleton', () => {
      expect(api).toBeDefined();
      expect(typeof api).toBe('object');
    });

    it('should export apiClient singleton', () => {
      expect(apiClient).toBeDefined();
      expect(typeof apiClient).toBe('object');
    });

    it('api and apiClient should reference the same instance', () => {
      expect(api).toBe(apiClient);
    });

    it('should have auth module', () => {
      expect(api.auth).toBeDefined();
      expect(typeof api.auth).toBe('object');
    });
  });

  describe('Auth Module', () => {
    it('should have login method', () => {
      expect(typeof api.auth.login).toBe('function');
    });

    it('should have logout method', () => {
      expect(typeof api.auth.logout).toBe('function');
    });

    it('should have register method', () => {
      expect(typeof api.auth.register).toBe('function');
    });

    it('should have getCurrentUser method', () => {
      expect(typeof api.auth.getCurrentUser).toBe('function');
    });

    it('should have refreshToken method', () => {
      expect(typeof api.auth.refreshToken).toBe('function');
    });

    it('should have getMockUsers method', () => {
      expect(typeof api.auth.getMockUsers).toBe('function');
    });

    it('should have mockSSOLogin method', () => {
      expect(typeof api.auth.mockSSOLogin).toBe('function');
    });
  });

  describe('Auth Module - Login Functionality', () => {
    it('should call login and set token on success', async () => {
      const mockResponse = {
        success: true,
        message: 'Login successful',
        data: {
          access_token: 'test-token-123',
          token_type: 'Bearer',
          expires_in: 3600,
          user: {
            id: '1',
            nycu_id: 'testuser',
            email: 'test@example.com',
            name: 'Test User',
            role: 'student' as const,
            created_at: '2025-01-01',
            updated_at: '2025-01-01',
          },
        },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await api.auth.login('testuser', 'password123');

      expect(result).toEqual(mockResponse);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/auth/login',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ username: 'testuser', password: 'password123' }),
        })
      );
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('auth_token', 'test-token-123');
    });

    it('should handle login failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ detail: 'Invalid credentials' }),
      });

      await expect(api.auth.login('wrong', 'credentials')).rejects.toThrow('Invalid credentials');
    });
  });

  describe('Auth Module - Logout Functionality', () => {
    it('should clear token on logout', async () => {
      // Set a token first
      apiClient.setToken('test-token');
      expect(apiClient.hasToken()).toBe(true);

      // Logout
      const result = await api.auth.logout();

      expect(result.success).toBe(true);
      expect(apiClient.hasToken()).toBe(false);
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('auth_token');
    });
  });

  describe('Token Management', () => {
    it('should set token correctly', () => {
      apiClient.setToken('new-token');
      expect(apiClient.getToken()).toBe('new-token');
      expect(apiClient.hasToken()).toBe(true);
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('auth_token', 'new-token');
    });

    it('should clear token correctly', () => {
      apiClient.setToken('token-to-clear');
      apiClient.clearToken();
      expect(apiClient.getToken()).toBe(null);
      expect(apiClient.hasToken()).toBe(false);
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('auth_token');
    });
  });

  describe('Request Method', () => {
    it('should make authenticated requests', async () => {
      apiClient.setToken('auth-token-123');

      const mockResponse = {
        success: true,
        message: 'Success',
        data: { id: 1, name: 'Test' },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve(mockResponse),
      });

      const result = await apiClient.request('/test-endpoint');

      expect(result).toEqual(mockResponse);
      const fetchCall = mockFetch.mock.calls[0];
      const headers = fetchCall[1].headers;
      expect(headers.get('Authorization')).toBe('Bearer auth-token-123');
    });

    it('should handle query parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: {} }),
      });

      await apiClient.request('/endpoint', {
        params: { page: 1, size: 10, filter: 'active' },
      });

      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/endpoint?page=1&size=10&filter=active');
    });
  });

  describe('Users Module', () => {
    beforeEach(() => {
      apiClient.setToken('test-token');
    });

    it('should have users module', () => {
      expect(api.users).toBeDefined();
      expect(typeof api.users).toBe('object');
    });

    it('should get user profile', async () => {
      const mockUser = {
        id: '1',
        nycu_id: 'testuser',
        email: 'test@example.com',
        name: 'Test User',
        role: 'student' as const,
        created_at: '2025-01-01',
        updated_at: '2025-01-01',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: mockUser }),
      });

      const result = await api.users.getProfile();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockUser);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/users/me',
        expect.any(Object)
      );
    });

    it('should update user profile', async () => {
      const updateData = { name: 'Updated Name' };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Updated', data: updateData }),
      });

      const result = await api.users.updateProfile(updateData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/users/me');
      expect(fetchCall[1].method).toBe('PUT');
    });

    it('should get all users with pagination', async () => {
      const mockResponse = {
        items: [],
        total: 0,
        page: 1,
        size: 10,
        pages: 0,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: mockResponse }),
      });

      await api.users.getAll({ page: 1, size: 10 });

      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/users?page=1&size=10');
    });
  });

  describe('Scholarships Module', () => {
    beforeEach(() => {
      apiClient.setToken('test-token');
    });

    it('should have scholarships module', () => {
      expect(api.scholarships).toBeDefined();
      expect(typeof api.scholarships).toBe('object');
    });

    it('should get eligible scholarships', async () => {
      const mockScholarships = [
        { id: 1, name: 'Test Scholarship' },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: mockScholarships }),
      });

      const result = await api.scholarships.getEligible();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockScholarships);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/scholarships/eligible',
        expect.any(Object)
      );
    });

    it('should get scholarship by ID', async () => {
      const mockScholarship = { id: 1, name: 'Test Scholarship' };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: mockScholarship }),
      });

      const result = await api.scholarships.getById(1);

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockScholarship);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/scholarships/1',
        expect.any(Object)
      );
    });

    it('should get all scholarships', async () => {
      const mockScholarships = [
        { id: 1, name: 'Scholarship 1' },
        { id: 2, name: 'Scholarship 2' },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: mockScholarships }),
      });

      const result = await api.scholarships.getAll();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockScholarships);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/scholarships',
        expect.any(Object)
      );
    });

    it('should create combined PhD scholarship', async () => {
      const phdData = {
        name: 'Combined PhD',
        name_en: 'Combined PhD',
        description: 'Test description',
        description_en: 'Test description',
        sub_scholarships: [
          {
            code: 'PHD001',
            name: 'Sub Scholarship',
            name_en: 'Sub Scholarship',
            description: 'Sub description',
            description_en: 'Sub description',
            sub_type: 'nstc' as const,
            amount: 50000,
          },
        ],
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Created', data: phdData }),
      });

      const result = await api.scholarships.createCombinedPhd(phdData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/scholarships/combined/phd');
      expect(fetchCall[1].method).toBe('POST');
    });
  });

  describe('Applications Module', () => {
    beforeEach(() => {
      apiClient.setToken('test-token');
    });

    it('should have applications module', () => {
      expect(api.applications).toBeDefined();
      expect(typeof api.applications).toBe('object');
    });

    it('should get my applications', async () => {
      const mockApplications = [
        { id: 1, scholarship_type: 'academic_excellence', status: 'submitted' },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: mockApplications }),
      });

      const result = await api.applications.getMyApplications();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockApplications);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/applications',
        expect.any(Object)
      );
    });

    it('should create application', async () => {
      const appData = {
        scholarship_type: 'academic_excellence',
        personal_statement: 'Test statement',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Created', data: { id: 1, ...appData } }),
      });

      const result = await api.applications.createApplication(appData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/applications');
      expect(fetchCall[1].method).toBe('POST');
    });

    it('should submit application', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Submitted', data: { id: 1, status: 'submitted' } }),
      });

      const result = await api.applications.submitApplication(1);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/applications/1/submit');
      expect(fetchCall[1].method).toBe('POST');
    });
  });

  describe('Notifications Module', () => {
    beforeEach(() => {
      apiClient.setToken('test-token');
    });

    it('should have notifications module', () => {
      expect(api.notifications).toBeDefined();
      expect(typeof api.notifications).toBe('object');
    });

    it('should get notifications', async () => {
      const mockNotifications = [
        { id: 1, title: 'Test', message: 'Test notification', is_read: false },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: mockNotifications }),
      });

      const result = await api.notifications.getNotifications();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockNotifications);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/notifications',
        expect.any(Object)
      );
    });

    it('should get unread count', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: 5 }),
      });

      const result = await api.notifications.getUnreadCount();

      expect(result.success).toBe(true);
      expect(result.data).toBe(5);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/notifications/unread-count',
        expect.any(Object)
      );
    });

    it('should mark notification as read', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Marked as read', data: { id: 1, is_read: true } }),
      });

      const result = await api.notifications.markAsRead(1);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/notifications/1/read');
      expect(fetchCall[1].method).toBe('PATCH');
    });
  });

  describe('Quota Module', () => {
    beforeEach(() => {
      apiClient.setToken('test-token');
    });

    it('should have quota module', () => {
      expect(api.quota).toBeDefined();
      expect(typeof api.quota).toBe('object');
    });

    it('should get available semesters', async () => {
      const mockSemesters = [
        { period: '2024-1', display_name: '2024 第一學期', quota_management_mode: 'matrix_based' },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: mockSemesters }),
      });

      const result = await api.quota.getAvailableSemesters();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockSemesters);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/scholarship-configurations/available-semesters',
        expect.any(Object)
      );
    });

    it('should get quota overview', async () => {
      const mockOverview = [
        { scholarship_type: 'phd', total_quota: 100, used_quota: 50, remaining_quota: 50 },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'OK', data: mockOverview }),
      });

      const result = await api.quota.getQuotaOverview('2024-1');

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockOverview);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/scholarship-configurations/overview/2024-1',
        expect.any(Object)
      );
    });

    it('should update matrix quota', async () => {
      const updateRequest = {
        academic_year: '2024-1',
        sub_type: 'nstc',
        college: 'engineering',
        total_quota: 50,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Updated', data: updateRequest }),
      });

      const result = await api.quota.updateMatrixQuota(updateRequest);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/scholarship-configurations/matrix-quota');
      expect(fetchCall[1].method).toBe('PUT');
    });
  });

  describe('Professor Module', () => {
    it('should have professor module', () => {
      expect(api.professor).toBeDefined();
    });

    it('should get applications for review', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({
          success: true,
          message: 'Applications retrieved',
          data: { items: [], total: 0, page: 1, size: 10 }
        }),
      });

      const result = await api.professor.getApplications('pending');

      expect(result.data).toEqual([]);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/professor/applications?status_filter=pending');
    });

    it('should get professor stats', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({
          success: true,
          message: 'Stats retrieved',
          data: { pending_reviews: 5, completed_reviews: 10, overdue_reviews: 2 }
        }),
      });

      const result = await api.professor.getStats();

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/professor/stats');
    });

    it('should submit professor review', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Review submitted', data: {} }),
      });

      const reviewData = {
        recommendation: 'Approved',
        items: [{ sub_type_code: 'A', is_recommended: true }]
      };
      const result = await api.professor.submitReview(1, reviewData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/professor/applications/1/review');
      expect(fetchCall[1].method).toBe('POST');
    });
  });

  describe('College Module', () => {
    it('should have college module', () => {
      expect(api.college).toBeDefined();
    });

    it('should get applications for college review', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Applications retrieved', data: [] }),
      });

      const result = await api.college.getApplicationsForReview('status=pending');

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/college/applications?status=pending');
    });

    it('should get college rankings', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Rankings retrieved', data: [] }),
      });

      const result = await api.college.getRankings(113, 'first');

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/college/rankings?academic_year=113&semester=first');
    });

    it('should create college ranking', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Ranking created', data: { id: 1 } }),
      });

      const rankingData = {
        scholarship_type_id: 1,
        sub_type_code: 'A',
        academic_year: 113,
        semester: 'first'
      };
      const result = await api.college.createRanking(rankingData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/college/rankings');
      expect(fetchCall[1].method).toBe('POST');
    });

    it('should get college statistics', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Stats retrieved', data: {} }),
      });

      const result = await api.college.getStatistics(113, 'first');

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/college/statistics?academic_year=113&semester=first');
    });
  });

  describe('Whitelist Module', () => {
    it('should have whitelist module', () => {
      expect(api.whitelist).toBeDefined();
    });

    it('should toggle scholarship whitelist', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Whitelist toggled', data: { success: true } }),
      });

      const result = await api.whitelist.toggleScholarshipWhitelist(1, true);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/scholarships/1/whitelist');
      expect(fetchCall[1].method).toBe('PATCH');
    });

    it('should get configuration whitelist', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Whitelist retrieved', data: [] }),
      });

      const result = await api.whitelist.getConfigurationWhitelist(1, { page: 1, size: 10 });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/scholarship-configurations/1/whitelist?page=1&size=10');
    });

    it('should batch add to whitelist', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({
          success: true,
          message: 'Students added',
          data: { success_count: 2, failed_items: [] }
        }),
      });

      const result = await api.whitelist.batchAddWhitelist(1, {
        students: [{ nycu_id: '001', sub_type: 'A' }]
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/scholarship-configurations/1/whitelist/batch');
      expect(fetchCall[1].method).toBe('POST');
    });
  });

  describe('System Settings Module', () => {
    it('should have systemSettings module', () => {
      expect(api.systemSettings).toBeDefined();
    });

    it('should get all configurations', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Configurations retrieved', data: [] }),
      });

      const result = await api.systemSettings.getConfigurations('email', true);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/system-settings?category=email&include_sensitive=true');
    });

    it('should validate configuration', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({
          success: true,
          message: 'Validation result',
          data: { valid: true, errors: [], warnings: [] }
        }),
      });

      const result = await api.systemSettings.validateConfiguration({
        key: 'test_key',
        value: 'test_value',
        data_type: 'string'
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/system-settings/validate');
      expect(fetchCall[1].method).toBe('POST');
    });
  });

  describe('Bank Verification Module', () => {
    it('should have bankVerification module', () => {
      expect(api.bankVerification).toBeDefined();
    });

    it('should verify single bank account', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({
          success: true,
          message: 'Verified',
          data: { application_id: 1, verified: true }
        }),
      });

      const result = await api.bankVerification.verifyBankAccount(1);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/admin/bank-verification');
      expect(fetchCall[1].method).toBe('POST');
    });

    it('should verify batch bank accounts', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({
          success: true,
          message: 'Batch verified',
          data: { total: 3, verified: 2, failed: 1, results: [] }
        }),
      });

      const result = await api.bankVerification.verifyBankAccountsBatch([1, 2, 3]);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/admin/bank-verification/batch');
      expect(fetchCall[1].method).toBe('POST');
    });
  });

  describe('Professor-Student Module', () => {
    it('should have professorStudent module', () => {
      expect(api.professorStudent).toBeDefined();
    });

    it('should get professor-student relationships', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Relationships retrieved', data: [] }),
      });

      const result = await api.professorStudent.getProfessorStudentRelationships({
        professor_id: 1,
        status: 'active'
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/professor-student?professor_id=1&status=active');
    });

    it('should create professor-student relationship', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Relationship created', data: { id: 1 } }),
      });

      const result = await api.professorStudent.createProfessorStudentRelationship({
        professor_id: 1,
        student_id: 2,
        relationship_type: 'advisor'
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/professor-student');
      expect(fetchCall[1].method).toBe('POST');
    });
  });

  describe('Email Automation Module', () => {
    it('should have emailAutomation module', () => {
      expect(api.emailAutomation).toBeDefined();
    });

    it('should get automation rules', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Rules retrieved', data: [] }),
      });

      const result = await api.emailAutomation.getRules({ is_active: true });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/email-automation?is_active=true');
    });

    it('should toggle automation rule', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ success: true, message: 'Rule toggled', data: {} }),
      });

      const result = await api.emailAutomation.toggleRule(1);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/email-automation/1/toggle');
      expect(fetchCall[1].method).toBe('PATCH');
    });
  });

  describe('Batch Import Module', () => {
    it('should have batchImport module', () => {
      expect(api.batchImport).toBeDefined();
    });

    it('should get batch import history', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({
          success: true,
          message: 'History retrieved',
          data: { items: [], total: 0 }
        }),
      });

      const result = await api.batchImport.getHistory({ limit: 10 });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/college/batch-import/history?limit=10');
    });

    it('should confirm batch import', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({
          success: true,
          message: 'Batch confirmed',
          data: { success_count: 10, failed_count: 0, errors: [], created_application_ids: [] }
        }),
      });

      const result = await api.batchImport.confirm('batch-123', true);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(fetchCall[0]).toBe('/api/v1/college/batch-import/batch-123/confirm');
      expect(fetchCall[1].method).toBe('POST');
    });
  });
});
