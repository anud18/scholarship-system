import { apiClient } from "../api";

// Mock fetch - use jest.fn() that's already on global.fetch from jest.setup.ts
const mockFetch = global.fetch as jest.Mock;

// Mock localStorage
const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
};
Object.defineProperty(window, "localStorage", {
  value: mockLocalStorage,
});

function getHeader(headers: any, name: string): string | null {
  if (headers instanceof Headers) {
    return headers.get(name);
  } else if (headers && typeof headers === "object") {
    return headers[name] || headers[name.toLowerCase()] || null;
  }
  return null;
}

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

describe("API Client", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLocalStorage.getItem.mockReturnValue(null);
  });

  describe("Authentication", () => {
    it("should login successfully with valid credentials", async () => {
      const mockResponse = {
        success: true,
        message: "Login successful",
        data: {
          access_token: "test-token",
          token_type: "Bearer",
        },
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

      const result = await apiClient.auth.login("testuser", "password");

      const fetchCall = mockFetch.mock.calls[0];
      const requestOrUrl = fetchCall[0];
      const optionsOrUndefined = fetchCall[1];

      expect(getUrl(requestOrUrl)).toBe("/api/v1/auth/login");
      expect(getMethod(requestOrUrl) || optionsOrUndefined?.method).toBe("POST");
      expect(getBody(requestOrUrl) || optionsOrUndefined?.body).toBe(
        JSON.stringify({ username: "testuser", password: "password" })
      );
      expect(result).toEqual(mockResponse);
    });

    it("should handle login failure", async () => {
      const mockErrorResponse = {
        detail: "Invalid credentials",
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockErrorResponse), {
          status: 401,
          headers: { "content-type": "application/json" },
        })
      );

      const result = await apiClient.auth.login("invalid", "credentials");
      expect(result.success).toBe(false);
      expect(result.message).toContain("Invalid credentials");
    });

    it("should get current user with valid token", async () => {
      const mockUser = {
        id: "1",
        username: "testuser",
        email: "test@example.com",
        role: "student",
        full_name: "Test User",
        is_active: true,
        created_at: "2025-01-01",
        updated_at: "2025-01-01",
      };

      const mockResponse = {
        success: true,
        message: "User retrieved",
        data: mockUser,
      };

      // Set token
      apiClient.setToken("test-token");

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

      const result = await apiClient.auth.getCurrentUser();

      const fetchCall = mockFetch.mock.calls[0];
      const requestOrUrl = fetchCall[0];
      const optionsOrUndefined = fetchCall[1];
      const headers = getRequestHeaders(requestOrUrl) || optionsOrUndefined?.headers;

      expect(getHeader(headers, "Authorization")).toBe("Bearer test-token");
      expect(result.data).toEqual(mockUser);
    });
  });

  describe("Applications", () => {
    beforeEach(() => {
      apiClient.setToken("test-token");
    });

    it("should fetch user applications", async () => {
      const mockApplications = [
        {
          id: 1,
          student_id: "student1",
          scholarship_type: "academic_excellence",
          status: "submitted",
          personal_statement: "Test statement",
          gpa_requirement_met: true,
          created_at: "2025-01-01",
          updated_at: "2025-01-01",
        },
      ];

      const mockResponse = {
        success: true,
        message: "Applications retrieved",
        data: mockApplications,
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

      const result = await apiClient.applications.getMyApplications();

      const fetchCall = mockFetch.mock.calls[0];
      const requestOrUrl = fetchCall[0];
      const optionsOrUndefined = fetchCall[1];
      const headers = getRequestHeaders(requestOrUrl) || optionsOrUndefined?.headers;

      expect(getUrl(requestOrUrl)).toContain("/applications");
      expect(getHeader(headers, "Authorization")).toBe(
        "Bearer test-token"
      );
      expect(result.data).toEqual(mockApplications);
    });

    it("should create new application", async () => {
      const applicationData = {
        scholarship_type: "academic_excellence",
        personal_statement: "I am a dedicated student...",
        expected_graduation_date: "2025-06-15",
      };

      const mockCreatedApplication = {
        id: 1,
        student_id: "student1",
        ...applicationData,
        status: "draft",
        gpa_requirement_met: true,
        created_at: "2025-01-01",
        updated_at: "2025-01-01",
      };

      const mockResponse = {
        success: true,
        message: "Application created",
        data: mockCreatedApplication,
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

      const result =
        await apiClient.applications.createApplication(applicationData);

      const fetchCall = mockFetch.mock.calls[0];
      const requestOrUrl = fetchCall[0];
      const optionsOrUndefined = fetchCall[1];
      const headers = getRequestHeaders(requestOrUrl) || optionsOrUndefined?.headers;

      expect(getUrl(requestOrUrl)).toContain("/applications");
      expect(getMethod(requestOrUrl) || optionsOrUndefined?.method).toBe("POST");
      expect(getBody(requestOrUrl) || optionsOrUndefined?.body).toBe(JSON.stringify(applicationData));
      expect(getHeader(headers, "Content-Type")).toBe("application/json");
      expect(getHeader(headers, "Authorization")).toBe("Bearer test-token");
      expect(result.data).toEqual(mockCreatedApplication);
    });

    it("should submit application", async () => {
      const applicationId = 1;
      const mockSubmittedApplication = {
        id: applicationId,
        status: "submitted",
        submitted_at: "2025-01-01T10:00:00Z",
      };

      const mockResponse = {
        success: true,
        message: "Application submitted",
        data: mockSubmittedApplication,
      };

      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
      );

      const result =
        await apiClient.applications.submitApplication(applicationId);

      const fetchCall = mockFetch.mock.calls[0];
      const requestOrUrl = fetchCall[0];
      const optionsOrUndefined = fetchCall[1];
      const headers = getRequestHeaders(requestOrUrl) || optionsOrUndefined?.headers;

      expect(getUrl(requestOrUrl)).toBe(
        `/api/v1/applications/${applicationId}/submit`
      );
      expect(getMethod(requestOrUrl) || optionsOrUndefined?.method).toBe("POST");
      expect(getHeader(headers, "Authorization")).toBe(
        "Bearer test-token"
      );

      expect(result.data?.status).toBe("submitted");
    });
  });

  describe("Token Management", () => {
    it("should set and clear tokens correctly", () => {
      const testToken = "test-token-123";

      apiClient.setToken(testToken);
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
        "auth_token",
        testToken
      );

      apiClient.clearToken();
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith("auth_token");
    });
  });

  describe("Error Handling", () => {
    it("should handle network errors", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Network error"));

      await expect(apiClient.auth.getCurrentUser()).rejects.toThrow(
        "Network error"
      );
    });

    it("should handle HTTP errors", async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: "Internal server error",
          }),
          {
            status: 500,
            headers: { "content-type": "application/json" },
          }
        )
      );

      const result = await apiClient.auth.getCurrentUser();
      expect(result.success).toBe(false);
      expect(result.message).toContain("Internal server error");
    });
  });
});
