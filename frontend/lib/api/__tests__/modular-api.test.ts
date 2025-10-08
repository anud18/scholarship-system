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
});
