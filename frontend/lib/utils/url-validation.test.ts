/**
 * Unit tests for URL validation utilities
 *
 * Tests security-critical URL validation and construction functions
 * to ensure protection against open redirect vulnerabilities.
 */

import { validateSameOriginUrl, buildSecurePreviewUrl, getAuthToken } from './url-validation';

describe('URL Validation Utilities', () => {
  // Mock window.location for tests
  beforeEach(() => {
    // Reset location mock
    delete (global as any).window;
    (global as any).window = {
      location: {
        origin: 'http://localhost:3000',
        href: 'http://localhost:3000',
      },
    };
  });

  describe('validateSameOriginUrl', () => {
    it('should accept valid relative URLs', () => {
      expect(validateSameOriginUrl('/api/v1/preview')).toBe('/api/v1/preview');
      expect(validateSameOriginUrl('/api/v1/preview?token=abc')).toBe('/api/v1/preview?token=abc');
      expect(validateSameOriginUrl('/files/document.pdf')).toBe('/files/document.pdf');
    });

    it('should accept relative URLs with query parameters', () => {
      const url = '/api/v1/preview?rosterId=123&token=xyz';
      expect(validateSameOriginUrl(url)).toBe(url);
    });

    it('should reject absolute external URLs', () => {
      expect(() => validateSameOriginUrl('http://evil.com')).toThrow();
      expect(() => validateSameOriginUrl('https://malicious.site')).toThrow();
      expect(() => validateSameOriginUrl('//evil.com/path')).toThrow();
    });

    it('should reject protocol-relative URLs', () => {
      expect(() => validateSameOriginUrl('//attacker.com/malicious')).toThrow();
    });

    it('should validate paths with encoded characters', () => {
      const url = '/api/v1/preview?name=%E6%B8%AC%E8%A9%A6';
      expect(validateSameOriginUrl(url)).toBe(url);
    });

    it('should handle URLs with fragments', () => {
      const url = '/api/v1/preview#section';
      const result = validateSameOriginUrl(url);
      expect(result).toContain('/api/v1/preview');
    });
  });

  describe('buildSecurePreviewUrl', () => {
    it('should build valid preview URLs for allowed endpoints', () => {
      const url = buildSecurePreviewUrl('/api/v1/preview', {
        rosterId: 123,
        token: 'test-token',
      });

      expect(url).toContain('/api/v1/preview');
      expect(url).toContain('rosterId=123');
      expect(url).toContain('token=test-token');
    });

    it('should build URLs for document example endpoint', () => {
      const url = buildSecurePreviewUrl('/api/v1/preview-document-example', {
        documentId: 456,
        token: 'abc123',
      });

      expect(url).toContain('/api/v1/preview-document-example');
      expect(url).toContain('documentId=456');
      expect(url).toContain('token=abc123');
    });

    it('should build URLs for download endpoint', () => {
      const url = buildSecurePreviewUrl('/api/v1/download', {
        fileId: 789,
        token: 'xyz789',
      });

      expect(url).toContain('/api/v1/download');
      expect(url).toContain('fileId=789');
      expect(url).toContain('token=xyz789');
    });

    it('should reject non-allowlisted endpoints', () => {
      expect(() =>
        buildSecurePreviewUrl('/api/v1/malicious', { token: 'x' })
      ).toThrow(/not in allowlist/);

      expect(() =>
        buildSecurePreviewUrl('/unauthorized/endpoint', { token: 'x' })
      ).toThrow(/not in allowlist/);
    });

    it('should handle multiple parameters correctly', () => {
      const url = buildSecurePreviewUrl('/api/v1/preview', {
        type: 'roster',
        rosterId: 123,
        token: 'mytoken',
        extra: 'param',
      });

      expect(url).toContain('type=roster');
      expect(url).toContain('rosterId=123');
      expect(url).toContain('token=mytoken');
      expect(url).toContain('extra=param');
    });

    it('should skip undefined and null parameters', () => {
      const url = buildSecurePreviewUrl('/api/v1/preview', {
        rosterId: 123,
        token: 'test',
        undefinedParam: undefined,
        nullParam: null as any,
      });

      expect(url).toContain('rosterId=123');
      expect(url).toContain('token=test');
      expect(url).not.toContain('undefinedParam');
      expect(url).not.toContain('nullParam');
    });

    it('should properly encode special characters in parameters', () => {
      const url = buildSecurePreviewUrl('/api/v1/preview', {
        name: '測試文件',
        token: 'token with spaces',
      });

      // URLSearchParams should encode these (spaces become +)
      expect(url).toContain('/api/v1/preview');
      expect(decodeURIComponent(url)).toContain('測試文件');
      // URLSearchParams encodes spaces as + which is valid
      expect(url).toMatch(/token=token(\+|%20)with(\+|%20)spaces/);
    });

    it('should handle numeric parameter values', () => {
      const url = buildSecurePreviewUrl('/api/v1/preview', {
        id: 12345,
        count: 0,
      });

      expect(url).toContain('id=12345');
      expect(url).toContain('count=0');
    });

    it('should prevent injection attacks via parameters', () => {
      // Attempt to inject malicious URL via parameter value
      const url = buildSecurePreviewUrl('/api/v1/preview', {
        token: 'http://evil.com',
        rosterId: '../../../etc/passwd',
      });

      // Should still be same-origin
      expect(url).toMatch(/^\/api\/v1\/preview/);
      // Parameter values should be encoded, not interpreted as URLs
      expect(decodeURIComponent(url)).toContain('http://evil.com'); // As string value, not URL
    });
  });

  describe('getAuthToken', () => {
    beforeEach(() => {
      // Clear storage before each test
      localStorage.clear();
      sessionStorage.clear();
    });

    it('should retrieve token from localStorage (auth_token)', () => {
      localStorage.setItem('auth_token', 'test-token-1');
      expect(getAuthToken()).toBe('test-token-1');
    });

    it('should fallback to localStorage (token)', () => {
      localStorage.setItem('token', 'test-token-2');
      expect(getAuthToken()).toBe('test-token-2');
    });

    it('should fallback to sessionStorage (auth_token)', () => {
      sessionStorage.setItem('auth_token', 'test-token-3');
      expect(getAuthToken()).toBe('test-token-3');
    });

    it('should fallback to sessionStorage (token)', () => {
      sessionStorage.setItem('token', 'test-token-4');
      expect(getAuthToken()).toBe('test-token-4');
    });

    it('should prioritize localStorage over sessionStorage', () => {
      localStorage.setItem('auth_token', 'local-token');
      sessionStorage.setItem('auth_token', 'session-token');
      expect(getAuthToken()).toBe('local-token');
    });

    it('should prioritize auth_token over token', () => {
      localStorage.setItem('auth_token', 'auth-token');
      localStorage.setItem('token', 'plain-token');
      expect(getAuthToken()).toBe('auth-token');
    });

    it('should return empty string if no token found', () => {
      expect(getAuthToken()).toBe('');
    });

    it('should handle null values in storage', () => {
      // Storage returns null for non-existent keys
      expect(getAuthToken()).toBe('');
    });
  });

  describe('Security Integration Tests', () => {
    beforeEach(() => {
      localStorage.clear();
      sessionStorage.clear();
    });

    it('should prevent open redirect attack via localStorage manipulation', () => {
      // Attacker tries to inject malicious URL via localStorage
      localStorage.setItem('auth_token', 'http://evil.com');

      const url = buildSecurePreviewUrl('/api/v1/preview', {
        rosterId: 123,
        token: getAuthToken(),
      });

      // URL should still be same-origin
      expect(url).toMatch(/^\/api\/v1\/preview/);
      // The malicious value is just a parameter value, not a redirect target
      expect(decodeURIComponent(url)).toContain('token=http://evil.com');
    });

    it('should prevent path traversal via parameters', () => {
      const url = buildSecurePreviewUrl('/api/v1/preview', {
        fileId: '../../../etc/passwd',
        token: 'test',
      });

      // Still same-origin, path traversal in parameter value is just a string
      expect(url).toMatch(/^\/api\/v1\/preview/);
      expect(decodeURIComponent(url)).toContain('fileId=../../../etc/passwd');
    });

    it('should prevent JavaScript injection via parameters', () => {
      const url = buildSecurePreviewUrl('/api/v1/preview', {
        token: 'javascript:alert(1)',
        rosterId: '<script>alert(1)</script>',
      });

      expect(url).toMatch(/^\/api\/v1\/preview/);
      // Should be encoded as parameter values
      expect(url).not.toContain('<script>');
    });

    it('should validate full workflow: storage → builder → validation', () => {
      localStorage.setItem('auth_token', 'valid-token-123');

      const url = buildSecurePreviewUrl('/api/v1/preview', {
        rosterId: 456,
        token: getAuthToken(),
      });

      // Ensure the URL passes final validation
      expect(() => validateSameOriginUrl(url)).not.toThrow();
      expect(url).toContain('rosterId=456');
      expect(url).toContain('token=valid-token-123');
    });
  });
});
