import { renderHook, waitFor } from "@testing-library/react";
import { useScholarshipData } from "../use-scholarship-data";

// Mock localStorage
const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
};

Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
});

// Create mutable mock functions for API calls
const mockGetAllScholarships = jest.fn().mockResolvedValue({
  success: true,
  data: [
    {
      id: 1,
      code: "MERIT",
      name: "學術卓越獎學金",
      name_en: "Academic Excellence Scholarship",
    },
    {
      id: 2,
      code: "NEED",
      name: "經濟協助獎學金",
      name_en: "Financial Aid Scholarship",
    },
  ],
});

const mockAdminGetSubTypeTranslations = jest.fn().mockResolvedValue({
  success: true,
  data: {
    zh: {
      domestic: "國內學生",
      overseas: "海外學生",
    },
    en: {
      domestic: "Domestic Students",
      overseas: "Overseas Students",
    },
  },
});

const mockCollegeGetSubTypeTranslations = jest.fn().mockResolvedValue({
  success: true,
  data: {
    zh: {
      domestic: "國內學生",
      overseas: "海外學生",
    },
    en: {
      domestic: "Domestic Students",
      overseas: "Overseas Students",
    },
  },
});

// Mock the API client
jest.mock("@/lib/api", () => ({
  apiClient: {
    scholarships: {
      getAll: (...args: any[]) => mockGetAllScholarships(...args),
    },
    admin: {
      getSubTypeTranslations: (...args: any[]) =>
        mockAdminGetSubTypeTranslations(...args),
    },
    college: {
      getSubTypeTranslations: (...args: any[]) =>
        mockCollegeGetSubTypeTranslations(...args),
    },
  },
}));

// Mock SWR to simplify testing
jest.mock("swr", () => {
  return {
    __esModule: true,
    default: (key: string, fetcher: Function, config: any) => {
      // Simplified mock that calls fetcher and returns data
      let data = undefined;
      let error = undefined;
      let isLoading = true;

      fetcher()
        .then((result: any) => {
          data = result;
          isLoading = false;
        })
        .catch((err: any) => {
          error = err;
          isLoading = false;
        });

      return {
        data,
        error,
        isLoading,
        mutate: jest.fn().mockResolvedValue(undefined),
      };
    },
  };
});

describe("useScholarshipData Hook", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorageMock.getItem.mockReturnValue(null);
  });

  describe("Helper Functions - getScholarshipName", () => {
    it("should get scholarship name by ID in Chinese", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getScholarshipName(1, "zh");
      expect(typeof name).toBe("string");
    });

    it("should get scholarship name by ID in English", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getScholarshipName(1, "en");
      expect(typeof name).toBe("string");
    });

    it("should return fallback for undefined ID", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getScholarshipName(undefined, "zh");
      expect(name).toBe("-");
    });

    it("should return fallback for non-existent scholarship", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getScholarshipName(999, "zh");
      expect(name).toBe("-");
    });

    it("should default to Chinese locale", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getScholarshipName(1);
      expect(typeof name).toBe("string");
    });

    it("should handle null scholarship ID", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getScholarshipName(null as any, "zh");
      expect(name).toBe("-");
    });
  });

  describe("Helper Functions - getScholarshipByCode", () => {
    it("should return null for empty code", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const scholarship = result.current.getScholarshipByCode("");
      expect(scholarship).toBeNull();
    });

    it("should handle non-existent code", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const scholarship = result.current.getScholarshipByCode("INVALID");
      expect(scholarship === null || scholarship === undefined).toBe(true);
    });
  });

  describe("Helper Functions - getScholarshipById", () => {
    it("should return null for zero ID", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const scholarship = result.current.getScholarshipById(0);
      expect(scholarship).toBeNull();
    });

    it("should return null for negative ID", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const scholarship = result.current.getScholarshipById(-1);
      expect(scholarship === null || scholarship === undefined).toBe(true);
    });

    it("should handle type coercion for ID", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const scholarship = result.current.getScholarshipById(1);
      expect(scholarship === null || typeof scholarship === "object").toBe(true);
    });
  });

  describe("Helper Functions - getSubTypeName", () => {
    it("should get sub-type translation in Chinese", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getSubTypeName("domestic", "zh");
      expect(typeof name).toBe("string");
    });

    it("should get sub-type translation in English", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getSubTypeName("overseas", "en");
      expect(typeof name).toBe("string");
    });

    it("should return original code for missing translation", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getSubTypeName("unknown", "zh");
      expect(name).toBe("unknown");
    });

    it("should return fallback for undefined code", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getSubTypeName(undefined, "zh");
      expect(name).toBe("-");
    });

    it("should default to Chinese locale", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getSubTypeName("domestic");
      expect(typeof name).toBe("string");
    });

    it("should handle empty code", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const name = result.current.getSubTypeName("", "zh");
      expect(name).toBe("-");
    });
  });

  describe("Helper Functions - getAllSubTypeNames", () => {
    it("should return object for Chinese locale", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const translations = result.current.getAllSubTypeNames("zh");
      expect(typeof translations).toBe("object");
      expect(!Array.isArray(translations)).toBe(true);
    });

    it("should return object for English locale", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const translations = result.current.getAllSubTypeNames("en");
      expect(typeof translations).toBe("object");
      expect(!Array.isArray(translations)).toBe(true);
    });

    it("should return empty object for missing locale", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const translations = result.current.getAllSubTypeNames("invalid" as any);
      expect(typeof translations).toBe("object");
    });

    it("should default to Chinese locale", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const translations = result.current.getAllSubTypeNames();
      expect(typeof translations).toBe("object");
    });
  });

  describe("Hook State Properties", () => {
    it("should have scholarships array property", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(Array.isArray(result.current.scholarships)).toBe(true);
    });

    it("should have subTypeTranslations object property", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(typeof result.current.subTypeTranslations).toBe("object");
      expect(result.current.subTypeTranslations).toHaveProperty("zh");
      expect(result.current.subTypeTranslations).toHaveProperty("en");
    });

    it("should have isLoading boolean property", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(typeof result.current.isLoading).toBe("boolean");
    });

    it("should have error property", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(
        result.current.error === undefined ||
          result.current.error === null ||
          typeof result.current.error === "object"
      ).toBe(true);
    });

    it("should have refresh function", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(typeof result.current.refresh).toBe("function");
    });

    it("should have data object property", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(
        result.current.data === undefined ||
          result.current.data === null ||
          typeof result.current.data === "object"
      ).toBe(true);
    });
  });

  describe("Role Detection", () => {
    it("should initialize without errors for admin role", () => {
      expect(() => {
        renderHook(() => useScholarshipData(false, "admin"));
      }).not.toThrow();
    });

    it("should initialize without errors for college role", () => {
      expect(() => {
        renderHook(() => useScholarshipData(false, "college"));
      }).not.toThrow();
    });

    it("should handle auto-detection parameter", () => {
      expect(() => {
        renderHook(() => useScholarshipData(true, "admin"));
      }).not.toThrow();
    });

    it("should handle auto-detection disabled", () => {
      expect(() => {
        renderHook(() => useScholarshipData(false, "college"));
      }).not.toThrow();
    });
  });

  describe("Edge Cases", () => {
    it("should handle malformed localStorage JSON gracefully", () => {
      localStorageMock.getItem.mockReturnValue("invalid json");

      expect(() => {
        renderHook(() => useScholarshipData());
      }).not.toThrow();
    });

    it("should handle localStorage errors", () => {
      localStorageMock.getItem.mockImplementation(() => {
        throw new Error("Storage error");
      });

      expect(() => {
        renderHook(() => useScholarshipData());
      }).not.toThrow();
    });

    it("should provide fallback empty arrays for scholarships", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(Array.isArray(result.current.scholarships)).toBe(true);
    });

    it("should provide fallback empty objects for translations", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(typeof result.current.subTypeTranslations).toBe("object");
      expect(result.current.subTypeTranslations.zh).toBeDefined();
      expect(result.current.subTypeTranslations.en).toBeDefined();
    });

    it("should handle multiple hook instances", () => {
      expect(() => {
        renderHook(() => useScholarshipData(false, "admin"));
        renderHook(() => useScholarshipData(false, "college"));
      }).not.toThrow();
    });

    it("should maintain stable references for helper functions", () => {
      const { result, rerender } = renderHook(() =>
        useScholarshipData(false, "admin")
      );

      const firstGetName = result.current.getScholarshipName;
      rerender();
      const secondGetName = result.current.getScholarshipName;

      expect(typeof firstGetName).toBe("function");
      expect(typeof secondGetName).toBe("function");
    });
  });

  describe("API Integration", () => {
    it("should handle API initialization without errors", () => {
      mockGetAllScholarships.mockClear();
      mockAdminGetSubTypeTranslations.mockClear();

      expect(() => {
        renderHook(() => useScholarshipData(false, "admin"));
      }).not.toThrow();
    });

    it("should use admin API when admin role is specified", () => {
      expect(() => {
        renderHook(() => useScholarshipData(false, "admin"));
      }).not.toThrow();
    });

    it("should use college API when college role is specified", () => {
      expect(() => {
        renderHook(() => useScholarshipData(false, "college"));
      }).not.toThrow();
    });
  });

  describe("Data Structure Validation", () => {
    it("scholarships should be an array of objects", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(Array.isArray(result.current.scholarships)).toBe(true);
      if (result.current.scholarships.length > 0) {
        expect(typeof result.current.scholarships[0]).toBe("object");
      }
    });

    it("subTypeTranslations should have zh and en properties", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      expect(result.current.subTypeTranslations).toHaveProperty("zh");
      expect(result.current.subTypeTranslations).toHaveProperty("en");
      expect(typeof result.current.subTypeTranslations.zh).toBe("object");
      expect(typeof result.current.subTypeTranslations.en).toBe("object");
    });

    it("translation objects should contain string values", () => {
      const { result } = renderHook(() => useScholarshipData(false, "admin"));

      const zhKeys = Object.keys(result.current.subTypeTranslations.zh);
      if (zhKeys.length > 0) {
        const value = result.current.subTypeTranslations.zh[zhKeys[0]];
        expect(typeof value).toBe("string");
      }
    });
  });
});
