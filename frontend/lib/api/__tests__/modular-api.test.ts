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
});
