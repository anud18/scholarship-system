/**
 * Tests for modular API structure
 *
 * This test verifies that the new modular API maintains the same interface
 * and behavior as the original monolithic api.ts.
 */

import { api, apiClient } from '../index';

// Mock fetch - use jest.fn() that's already on global.fetch from jest.setup.ts
const mockFetch = global.fetch as jest.Mock;

// Mock localStorage
const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
};
Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage,
});


function getUrl(requestOrUrl: any): string {
  if (typeof requestOrUrl === 'string') {
    return requestOrUrl;
  }
  if (requestOrUrl && typeof requestOrUrl === 'object' && 'url' in requestOrUrl) {
    return requestOrUrl.url;
  }
  return String(requestOrUrl);
}

function getMethod(requestOrOptions: any): string | undefined {
  if (requestOrOptions && typeof requestOrOptions === 'object' && 'method' in requestOrOptions) {
    return requestOrOptions.method;
  }
  return undefined;
}

function getRequestHeaders(requestOrOptions: any): any {
  if (requestOrOptions && typeof requestOrOptions === 'object' && 'headers' in requestOrOptions) {
    return requestOrOptions.headers;
  }
  return null;
}

function getBody(requestOrOptions: any): any {
  if (requestOrOptions && typeof requestOrOptions === 'object') {
    // For Request objects from whatwg-fetch
    if ('_bodyInit' in requestOrOptions && requestOrOptions._bodyInit instanceof FormData) {
      return requestOrOptions._bodyInit;
    }
    if ('_bodyText' in requestOrOptions) {
      return requestOrOptions._bodyText;
    }
    // For plain options objects
    if ('body' in requestOrOptions) {
      return requestOrOptions.body;
    }
  }
  return undefined;
}

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

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.auth.login('testuser', 'password123');

      expect(result).toEqual(mockResponse);
      const fetchCall = (mockFetch as jest.Mock).mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/auth/login');
      expect(getMethod(fetchCall[0])).toBe('POST');
      expect(getBody(fetchCall[0])).toBe(JSON.stringify({ username: 'testuser', password: 'password123' }));
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('auth_token', 'test-token-123');
    });

    it('should handle login failure', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Invalid credentials' }), {
        status: 401,
        statusText: 'Unauthorized',
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.auth.login('wrong', 'credentials');

      expect(result.success).toBe(false);
      expect(result.message).toBe('Invalid credentials');
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

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await apiClient.request('/test-endpoint');

      expect(result).toEqual(mockResponse);
      const fetchCall = mockFetch.mock.calls[0];
      const headers = getRequestHeaders(fetchCall[0]) || fetchCall[1]?.headers;
      expect(headers.get('Authorization')).toBe('Bearer auth-token-123');
    });

    it('should handle query parameters', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: {} }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      await apiClient.request('/endpoint', {
        params: { page: 1, size: 10, filter: 'active' },
      });

      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/endpoint?page=1&size=10&filter=active');
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

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: mockUser }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.users.getProfile();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockUser);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/users/me');
    });

    it('should update user profile', async () => {
      const updateData = { name: 'Updated Name' };

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Updated', data: updateData }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.users.updateProfile(updateData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/users/me');
      expect(getMethod(fetchCall[0])).toBe('PUT');
    });

    it('should get all users with pagination', async () => {
      const mockResponse = {
        items: [],
        total: 0,
        page: 1,
        size: 10,
        pages: 0,
      };

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: mockResponse }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      await api.users.getAll({ page: 1, size: 10 });

      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/users?page=1&size=10');
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

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: mockScholarships }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.scholarships.getEligible();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockScholarships);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/scholarships/eligible');
    });

    it('should get scholarship by ID', async () => {
      const mockScholarship = { id: 1, name: 'Test Scholarship' };

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: mockScholarship }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.scholarships.getById(1);

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockScholarship);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/scholarships/1');
    });

    it('should get all scholarships', async () => {
      const mockScholarships = [
        { id: 1, name: 'Scholarship 1' },
        { id: 2, name: 'Scholarship 2' },
      ];

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: mockScholarships }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.scholarships.getAll();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockScholarships);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/scholarships');
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

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Created', data: phdData }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.scholarships.createCombinedPhd(phdData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/scholarships/combined/phd');
      expect(getMethod(fetchCall[0])).toBe('POST');
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

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: mockApplications }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.applications.getMyApplications();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockApplications);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/applications');
    });

    it('should create application', async () => {
      const appData = {
        scholarship_type: 'academic_excellence',
        personal_statement: 'Test statement',
      };

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Created', data: { id: 1, ...appData } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.applications.createApplication(appData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/applications');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });

    it('should submit application', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Submitted', data: { id: 1, status: 'submitted' } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.applications.submitApplication(1);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/applications/1/submit');
      expect(getMethod(fetchCall[0])).toBe('POST');
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

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: mockNotifications }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.notifications.getNotifications();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockNotifications);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/notifications');
    });

    it('should get unread count', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: 5 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.notifications.getUnreadCount();

      expect(result.success).toBe(true);
      expect(result.data).toBe(5);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/notifications/unread-count');
    });

    it('should mark notification as read', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Marked as read', data: { id: 1, is_read: true } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.notifications.markAsRead(1);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/notifications/1/read');
      expect(getMethod(fetchCall[0])).toBe('PATCH');
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

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: mockSemesters }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.quota.getAvailableSemesters();

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockSemesters);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/scholarship-configurations/available-semesters');
    });

    it('should get quota overview', async () => {
      const mockOverview = [
        { scholarship_type: 'phd', total_quota: 100, used_quota: 50, remaining_quota: 50 },
      ];

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'OK', data: mockOverview }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.quota.getQuotaOverview('2024-1');

      expect(result.success).toBe(true);
      expect(result.data).toEqual(mockOverview);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/scholarship-configurations/overview/2024-1');
    });

    it('should update matrix quota', async () => {
      const updateRequest = {
        academic_year: '2024-1',
        sub_type: 'nstc',
        college: 'engineering',
        total_quota: 50,
      };

      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Updated', data: updateRequest }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.quota.updateMatrixQuota(updateRequest);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/scholarship-configurations/matrix-quota');
      expect(getMethod(fetchCall[0])).toBe('PUT');
    });
  });

  describe('Professor Module', () => {
    it('should have professor module', () => {
      expect(api.professor).toBeDefined();
    });

    it('should get applications for review', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Applications retrieved',
          data: { items: [], total: 0, page: 1, size: 10 }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.professor.getApplications('pending');

      expect(result.data).toEqual([]);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/professor/applications?status_filter=pending');
    });

    it('should get professor stats', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Stats retrieved',
          data: { pending_reviews: 5, completed_reviews: 10, overdue_reviews: 2 }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.professor.getStats();

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/professor/stats');
    });

    it('should submit professor review', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Review submitted', data: {} }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const reviewData = {
        recommendation: 'Approved',
        items: [{ sub_type_code: 'A', is_recommended: true }]
      };
      const result = await api.professor.submitReview(1, reviewData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/professor/applications/1/review');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });
  });

  describe('College Module', () => {
    it('should have college module', () => {
      expect(api.college).toBeDefined();
    });

    it('should get applications for college review', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Applications retrieved', data: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.college.getApplicationsForReview('status=pending');

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/college');
    });

    it('should get college rankings', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Rankings retrieved', data: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.college.getRankings(113, 'first');

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/college-review/rankings?academic_year=113&semester=first');
    });

    it('should create college ranking', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Ranking created', data: { id: 1 } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const rankingData = {
        scholarship_type_id: 1,
        sub_type_code: 'A',
        academic_year: 113,
        semester: 'first'
      };
      const result = await api.college.createRanking(rankingData);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/college-review/rankings');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });

    it('should get college statistics', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Stats retrieved', data: {} }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.college.getStatistics(113, 'first');

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/college-review/statistics?academic_year=113&semester=first');
    });
  });

  describe('Whitelist Module', () => {
    it('should have whitelist module', () => {
      expect(api.whitelist).toBeDefined();
    });

    it('should toggle scholarship whitelist', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Whitelist toggled', data: { success: true } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.whitelist.toggleScholarshipWhitelist(1, true);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/scholarships/1/whitelist');
      expect(getMethod(fetchCall[0])).toBe('PATCH');
    });

    it('should get configuration whitelist', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Whitelist retrieved', data: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.whitelist.getConfigurationWhitelist(1, { page: 1, size: 10 });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/scholarship-configurations/1/whitelist?page=1&size=10');
    });

    it('should batch add to whitelist', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Students added',
          data: { success_count: 2, failed_items: [] }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.whitelist.batchAddWhitelist(1, {
        students: [{ nycu_id: '001', sub_type: 'A' }]
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/scholarship-configurations/1/whitelist/batch');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });
  });

  describe('System Settings Module', () => {
    it('should have systemSettings module', () => {
      expect(api.systemSettings).toBeDefined();
    });

    it('should get all configurations', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Configurations retrieved', data: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.systemSettings.getConfigurations('email', true);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/system-settings');
      expect(getUrl(fetchCall[0])).toContain('category=email');
      expect(getUrl(fetchCall[0])).toContain('include_sensitive=true');
    });

    it('should validate configuration', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Validation result',
          data: { valid: true, errors: [], warnings: [] }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.systemSettings.validateConfiguration({
        key: 'test_key',
        value: 'test_value',
        data_type: 'string'
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/system-settings/validate');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });
  });

  describe('Bank Verification Module', () => {
    it('should have bankVerification module', () => {
      expect(api.bankVerification).toBeDefined();
    });

    it('should verify single bank account', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Verified',
          data: { application_id: 1, verified: true }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.bankVerification.verifyBankAccount(1);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/admin/bank-verification');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });

    it('should verify batch bank accounts', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Batch verified',
          data: { total: 3, verified: 2, failed: 1, results: [] }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.bankVerification.verifyBankAccountsBatch([1, 2, 3]);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/admin/bank-verification/batch');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });
  });

  describe('Professor-Student Module', () => {
    it('should have professorStudent module', () => {
      expect(api.professorStudent).toBeDefined();
    });

    it('should get professor-student relationships', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Relationships retrieved', data: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.professorStudent.getProfessorStudentRelationships({
        professor_id: 1,
        status: 'active'
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/professor-student?professor_id=1&status=active');
    });

    it('should create professor-student relationship', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Relationship created', data: { id: 1 } }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.professorStudent.createProfessorStudentRelationship({
        professor_id: 1,
        student_id: 2,
        relationship_type: 'advisor'
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/professor-student');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });
  });

  describe('Email Automation Module', () => {
    it('should have emailAutomation module', () => {
      expect(api.emailAutomation).toBeDefined();
    });

    it('should get automation rules', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Rules retrieved', data: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.emailAutomation.getRules({ is_active: true });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/email-automation?is_active=true');
    });

    it('should toggle automation rule', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ success: true, message: 'Rule toggled', data: {} }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.emailAutomation.toggleRule(1);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/email-automation/1/toggle');
      expect(getMethod(fetchCall[0])).toBe('PATCH');
    });
  });

  describe('Batch Import Module', () => {
    it('should have batchImport module', () => {
      expect(api.batchImport).toBeDefined();
    });

    it('should get batch import history', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'History retrieved',
          data: { items: [], total: 0 }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.batchImport.getHistory({ limit: 10 });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/college-review/batch-import/history');
      expect(getUrl(fetchCall[0])).toContain('limit=10');
    });

    it('should confirm batch import', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Batch confirmed',
          data: { success_count: 10, failed_count: 0, errors: [], created_application_ids: [] }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.batchImport.confirm('batch-123', true);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/college-review/batch-import/batch-123/confirm');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });
  });

  describe('Reference Data Module', () => {
    it('should have referenceData module', () => {
      expect(api.referenceData).toBeDefined();
    });

    it('should get all academies', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Academies retrieved',
          data: [{ id: 1, code: 'CS', name: 'Computer Science' }]
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.referenceData.getAcademies();

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/reference-data/academies');
    });

    it('should get all reference data', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Reference data retrieved',
          data: {
            academies: [],
            departments: [],
            degrees: [],
            identities: [],
            studying_statuses: [],
            school_identities: [],
            enroll_types: []
          }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.referenceData.getAll();

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/reference-data/all');
    });

    it('should get scholarship periods', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Periods retrieved',
          data: {
            periods: [],
            cycle: 'semester',
            scholarship_name: 'Test',
            current_period: '113-1',
            total_periods: 2
          }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.referenceData.getScholarshipPeriods({
        scholarship_id: 1,
        application_cycle: 'semester'
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/reference-data/scholarship-periods?scholarship_id=1&application_cycle=semester');
    });
  });

  describe('Application Fields Module', () => {
    it('should have applicationFields module', () => {
      expect(api.applicationFields).toBeDefined();
    });

    it('should get form config', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Form config retrieved',
          data: { scholarship_type: 'test', fields: [], documents: [] }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.applicationFields.getFormConfig('test', false);

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/application-fields/form-config/test?include_inactive=false');
    });

    it('should create field', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Field created',
          data: {
            id: 1,
            scholarship_type: 'test',
            field_name: 'custom_field',
            field_label: 'Custom Field',
            field_type: 'text',
            required: false,
            display_order: 1,
            is_active: true
          }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.applicationFields.createField({
        scholarship_type: 'test',
        field_name: 'custom_field',
        field_label: 'Custom Field',
        field_type: 'text',
        required: false,
        display_order: 1,
        is_active: true
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/application-fields/fields');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });

    it('should get documents', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Documents retrieved',
          data: []
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.applicationFields.getDocuments('test');

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/application-fields/documents/test');
    });
  });

  describe('User Profiles Module', () => {
    it('should have userProfiles module', () => {
      expect(api.userProfiles).toBeDefined();
    });

    it('should get my profile', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Profile retrieved',
          data: {
            user_id: 1,
            nycu_id: 'test123',
            full_name: 'Test User',
            email: 'test@example.com'
          }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.userProfiles.getMyProfile();

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/user-profiles/me');
    });

    it('should update bank info', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Bank info updated',
          data: {}
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.userProfiles.updateBankInfo({
        bank_account: '1234567890',
        bank_name: 'Test Bank',
        bank_branch: 'Main Branch'
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/user-profiles/me/bank-info');
      expect(getMethod(fetchCall[0])).toBe('PUT');
    });

    it('should get incomplete profiles (admin)', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Incomplete profiles retrieved',
          data: []
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.userProfiles.admin.getIncompleteProfiles();

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/user-profiles/admin/incomplete');
    });
  });

  describe('Email Management Module', () => {
    it('should have emailManagement module', () => {
      expect(api.emailManagement).toBeDefined();
    });

    it('should get email history', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Email history retrieved',
          data: {
            items: [],
            total: 0,
            skip: 0,
            limit: 10
          }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.emailManagement.getEmailHistory({ limit: 10, status: 'sent' });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/email-management/history');
    });

    it('should approve scheduled email', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Email approved',
          data: {}
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.emailManagement.approveScheduledEmail(1, 'Looks good');

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/email-management/scheduled/1/approve');
      expect(getMethod(fetchCall[0])).toBe('PATCH');
    });

    it('should get test mode status', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Test mode status retrieved',
          data: {
            enabled: false,
            redirect_emails: [],
            expires_at: null
          }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.emailManagement.getTestModeStatus();

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/email-management/test-mode/status');
    });

    it('should enable test mode', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Test mode enabled',
          data: {
            enabled: true,
            redirect_emails: ['test@example.com'],
            expires_at: '2025-10-09T00:00:00Z',
            enabled_by: 1,
            enabled_at: '2025-10-08T00:00:00Z'
          }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.emailManagement.enableTestMode({
        redirect_emails: ['test@example.com'],
        duration_hours: 24
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toContain('/api/v1/email-management/test-mode/enable');
      expect(getUrl(fetchCall[0])).toContain('redirect_emails=test%40example.com'); // @ is URL-encoded to %40
      expect(getUrl(fetchCall[0])).toContain('duration_hours=24');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });
  });

  describe('Admin Module', () => {
    it('should have admin module', () => {
      expect(api.admin).toBeDefined();
    });

    it('should get dashboard stats', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Dashboard stats retrieved',
          data: { total_applications: 100, total_scholarships: 10 }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.admin.getDashboardStats();

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/admin/dashboard/stats');
    });

    it('should get all applications', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Applications retrieved',
          data: { items: [], total: 0, page: 1, size: 10 }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.admin.getAllApplications(1, 10, 'pending');

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/admin/applications?page=1&size=10&status=pending');
    });

    it('should create announcement', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Announcement created',
          data: { id: 1, title: 'Test Announcement' }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.admin.createAnnouncement({ title: 'Test', content: 'Test content' });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/admin/announcements');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });

    it('should get scholarship rules', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Rules retrieved',
          data: []
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.admin.getScholarshipRules({ scholarship_type_id: 1 });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/admin/scholarship-rules?scholarship_type_id=1');
    });

    it('should create scholarship configuration', async () => {
      mockFetch.mockResolvedValueOnce(
      new Response(JSON.stringify({
          success: true,
          message: 'Configuration created',
          data: { id: 1, config_code: 'TEST-113-1' }
        }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );

      const result = await api.admin.createScholarshipConfiguration({
        scholarship_type_id: 1,
        academic_year: 113,
        semester: 'first'
      });

      expect(result.success).toBe(true);
      const fetchCall = mockFetch.mock.calls[0];
      expect(getUrl(fetchCall[0])).toBe('/api/v1/scholarship-configurations/configurations');
      expect(getMethod(fetchCall[0])).toBe('POST');
    });
  });
});
