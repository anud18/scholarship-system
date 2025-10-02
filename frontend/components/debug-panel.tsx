"use client";

import { useState, useEffect, useRef } from "react";
import type { JSX } from "react";
import {
  X,
  Bug,
  ChevronDown,
  ChevronRight,
  Copy,
  CheckCircle2,
  Server,
  Cloud,
  Settings,
  Database,
  RefreshCw,
} from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { apiClient } from "@/lib/api";

interface DebugPanelProps {
  isTestMode?: boolean;
}

export function DebugPanel({ isTestMode = false }: DebugPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [portalData, setPortalData] = useState<any>(null);
  const [studentData, setStudentData] = useState<any>(null);
  const [jwtData, setJwtData] = useState<any>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(["jwt", "portal", "student"])
  );
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<Set<string>>(new Set());
  const [dataSourceInfo, setDataSourceInfo] = useState({
    portalSource: "unknown" as "mock" | "real" | "unknown",
    studentApiSource: "unknown" as "mock" | "real" | "unknown",
    environment: "unknown" as "dev" | "test" | "prod" | "unknown",
  });
  const { user, token } = useAuth();
  const dialogRef = useRef<HTMLDivElement>(null);

  // Only show when explicitly enabled via environment variable or in test mode
  const isTestEnvironment = () => {
    if (typeof window === 'undefined') return false;
    const hostname = window.location.hostname;
    return hostname.includes("test") || hostname.includes("staging") || hostname.includes("localhost") || hostname === "140.113.7.148";
  };

  const shouldShow =
    isTestMode ||
    process.env.NODE_ENV === "development" ||
    isTestEnvironment();

  // Handle modal focus management and escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    // Focus the dialog when it opens
    if (dialogRef.current) {
      dialogRef.current.focus();
    }

    // Prevent body scroll when modal is open
    document.body.style.overflow = "hidden";

    // Add keydown listener
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      // Restore body scroll
      document.body.style.overflow = "";
      // Remove keydown listener
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  // Helper functions to detect data sources
  const detectEnvironment = (): "dev" | "test" | "prod" | "unknown" => {
    if (typeof window === "undefined") return "unknown";

    const hostname = window.location.hostname;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return "dev";
    } else if (hostname === "140.113.7.148") {
      return "test";
    } else if (hostname.includes("prod") || hostname.includes("nycu.edu.tw")) {
      return "prod";
    }
    return "unknown";
  };

  const detectPortalSource = (
    jwtPayload: any,
    portalData: any
  ): "mock" | "real" | "unknown" => {
    // If JWT has debug_mode flag, check portal data source
    if (jwtPayload?.debug_mode && portalData) {
      // Mock portal data typically has fewer fields and simpler structure
      // Real portal data has more complex nested structures
      if (portalData.source === "mock" || portalData.mock === true) {
        return "mock";
      }
      // Check if it has characteristics of mock data
      if (
        typeof portalData.nycu_id === "string" &&
        portalData.nycu_id.startsWith("dev_")
      ) {
        return "mock";
      }
      // Check for Portal SSO specific fields
      if (portalData.portal_session_id || portalData.portal_jwt_verified) {
        return "real";
      }
    }

    // Check environment to make educated guess
    const env = detectEnvironment();
    if (env === "dev") return "mock";
    if (env === "test" || env === "prod") return "real"; // Test mode uses real Portal SSO

    return "unknown";
  };

  const detectStudentApiSource = (
    jwtPayload: any,
    studentData: any
  ): "mock" | "real" | "unknown" => {
    // If JWT has debug_mode flag, check student data source
    if (jwtPayload?.debug_mode && studentData) {
      // Mock student API data has specific characteristics
      if (studentData.source === "mock" || studentData.mock === true) {
        return "mock";
      }
      // Check if API URL points to mock service
      if (
        studentData.api_url &&
        studentData.api_url.includes("mock-student-api")
      ) {
        return "mock";
      }
      // Check for mock data patterns
      if (
        studentData.student_id &&
        studentData.student_id.toString().startsWith("999")
      ) {
        return "mock";
      }
    }

    // Check environment - dev and test use mock student API, prod uses real API
    const env = detectEnvironment();
    if (env === "dev" || env === "test") return "mock"; // Test mode uses mock Student API for backdrop
    if (env === "prod") return "real";

    return "unknown";
  };

  // Function to fetch live student data from API
  const fetchStudentData = async () => {
    if (!user || !token) return;

    // Only students can access student information
    if (user.role !== "student") {
      setStudentData({
        source: "api_live",
        api_endpoint: "/users/student-info",
        timestamp: new Date().toISOString(),
        error: "Student information only available for student accounts",
      });
      return;
    }

    setIsRefreshing(prev => new Set(prev).add("student"));
    try {
      console.log("🔍 Fetching live student data from API...");
      const response = await apiClient.users.getStudentInfo();
      if (response.success && response.data) {
        console.log("🔍 Live student data fetched:", response.data);
        console.log("🔍 Semesters data:", response.data.semesters);
        setStudentData({
          source: "api_live",
          api_endpoint: "/users/student-info",
          timestamp: new Date().toISOString(),
          ...response.data,
        });
      } else {
        console.log("🔍 Student API returned no data:", response.message);
        setStudentData({
          source: "api_live",
          api_endpoint: "/users/student-info",
          timestamp: new Date().toISOString(),
          error: response.message || "No data available",
        });
      }
    } catch (error) {
      console.error("🔍 Failed to fetch student data:", error);
      setStudentData({
        source: "api_live",
        api_endpoint: "/users/student-info",
        timestamp: new Date().toISOString(),
        error: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setIsRefreshing(prev => {
        const newSet = new Set(prev);
        newSet.delete("student");
        return newSet;
      });
    }
  };

  // Function to fetch portal data (from JWT and current user data)
  const fetchPortalData = async () => {
    if (!user || !token) return;

    setIsRefreshing(prev => new Set(prev).add("portal"));
    try {
      console.log("🔍 Assembling portal data from current user and JWT...");

      // Get current user profile which contains portal-sourced data
      const response = await apiClient.users.getProfile();
      if (response.success && response.data) {
        console.log("🔍 Portal-sourced user data:", response.data);
        setPortalData({
          source: "api_live",
          api_endpoint: "/users/me",
          timestamp: new Date().toISOString(),
          user_profile: response.data,
          jwt_claims: jwtData
            ? {
                sub: jwtData.sub,
                nycu_id: jwtData.nycu_id,
                role: jwtData.role,
                exp: jwtData.exp,
                iat: jwtData.iat,
              }
            : null,
        });
      } else {
        console.log("🔍 Portal API returned no data:", response.message);
        setPortalData({
          source: "api_live",
          api_endpoint: "/users/me",
          timestamp: new Date().toISOString(),
          error: response.message || "No data available",
        });
      }
    } catch (error) {
      console.error("🔍 Failed to fetch portal data:", error);
      setPortalData({
        source: "api_live",
        api_endpoint: "/users/me",
        timestamp: new Date().toISOString(),
        error: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setIsRefreshing(prev => {
        const newSet = new Set(prev);
        newSet.delete("portal");
        return newSet;
      });
    }
  };

  useEffect(() => {
    if (!shouldShow || !token) {
      console.log("🔍 Debug Panel: No token available or not in debug mode");
      return;
    }

    console.log(
      "🔍 Debug Panel: Processing token:",
      token.substring(0, 50) + "..."
    );

    // Decode JWT to get portal data
    try {
      const parts = token.split(".");
      console.log("🔍 JWT Parts count:", parts.length);

      if (parts.length === 3) {
        // Add padding if needed for base64 decoding
        let payload = parts[1];
        while (payload.length % 4) {
          payload += "=";
        }

        console.log(
          "🔍 Decoding JWT payload:",
          payload.substring(0, 50) + "..."
        );
        const decodedPayload = JSON.parse(atob(payload));
        console.log("🔍 Decoded JWT payload:", decodedPayload);

        setJwtData(decodedPayload);

        // Extract portal data from JWT
        if (decodedPayload.portal_data) {
          console.log(
            "🔍 Found portal_data in JWT:",
            decodedPayload.portal_data
          );
          setPortalData(decodedPayload.portal_data);
        } else {
          console.log("🔍 No portal_data found in JWT");
        }

        // Extract student data from JWT
        if (decodedPayload.student_data) {
          console.log(
            "🔍 Found student_data in JWT:",
            decodedPayload.student_data
          );
          setStudentData(decodedPayload.student_data);
        } else {
          console.log("🔍 No student_data found in JWT");
        }

        // Detect data sources based on JWT payload and environment
        const newDataSourceInfo = {
          portalSource: detectPortalSource(decodedPayload, portalData),
          studentApiSource: detectStudentApiSource(decodedPayload, studentData),
          environment: detectEnvironment(),
        };
        console.log("🔍 Detected data sources:", newDataSourceInfo);
        setDataSourceInfo(newDataSourceInfo);

        // Auto-fetch live API data when panel loads
        console.log("🔍 Auto-fetching live API data...");
        fetchStudentData();
        fetchPortalData();
      } else {
        console.error(
          "🔍 Invalid JWT format - expected 3 parts, got:",
          parts.length
        );
      }
    } catch (error) {
      console.error("🔍 Failed to decode JWT:", error);
      console.error(
        "🔍 Token parts:",
        token
          .split(".")
          .map((part, i) => `Part ${i}: ${part.substring(0, 20)}...`)
      );
    }
  }, [token, shouldShow]);

  if (!shouldShow) return null;

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  };

  const copyToClipboard = async (text: string, field: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    } catch (error) {
      console.error("Failed to copy:", error);
    }
  };

  const renderValue = (value: any, path: string = ""): JSX.Element => {
    if (value === null || value === undefined) {
      return <span className="text-gray-400">null</span>;
    }

    if (typeof value === "boolean") {
      return (
        <span className={value ? "text-green-600" : "text-red-600"}>
          {String(value)}
        </span>
      );
    }

    if (typeof value === "string" || typeof value === "number") {
      const stringValue = String(value);
      return (
        <div className="flex items-center gap-1 group">
          <span className="text-blue-600">{stringValue}</span>
          <button
            onClick={() => copyToClipboard(stringValue, path)}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:bg-gray-100 rounded"
            title="Copy to clipboard"
          >
            {copiedField === path ? (
              <CheckCircle2 className="w-3 h-3 text-green-600" />
            ) : (
              <Copy className="w-3 h-3 text-gray-400" />
            )}
          </button>
        </div>
      );
    }

    if (Array.isArray(value)) {
      return (
        <div className="ml-4">
          <span className="text-gray-500">[{value.length} items]</span>
          {value.map((item, index) => (
            <div key={index} className="ml-2 my-1">
              <span className="text-gray-400">{index}:</span>{" "}
              {renderValue(item, `${path}[${index}]`)}
            </div>
          ))}
        </div>
      );
    }

    if (typeof value === "object") {
      return (
        <div className="ml-4">
          {Object.entries(value).map(([key, val]) => (
            <div key={key} className="my-1">
              <span className="text-purple-600">{key}:</span>{" "}
              {renderValue(val, `${path}.${key}`)}
            </div>
          ))}
        </div>
      );
    }

    return <span className="text-gray-600">{JSON.stringify(value)}</span>;
  };

  const getSourceBadge = (
    sourceType: "mock" | "real" | "unknown",
    label: string
  ) => {
    const getBadgeColor = () => {
      switch (sourceType) {
        case "mock":
          return "bg-orange-100 text-orange-700 border-orange-200";
        case "real":
          return "bg-green-100 text-green-700 border-green-200";
        case "unknown":
          return "bg-gray-100 text-gray-700 border-gray-200";
      }
    };

    const getBadgeIcon = () => {
      switch (sourceType) {
        case "mock":
          return <Settings className="w-3 h-3" />;
        case "real":
          return <Cloud className="w-3 h-3" />;
        case "unknown":
          return <Database className="w-3 h-3" />;
      }
    };

    const getBadgeText = () => {
      if (label === "API" && sourceType === "mock") {
        // Special case for Student API - clarify that mock means backdrop API
        return "Real API (Mock Backdrop)";
      }
      return `${sourceType.charAt(0).toUpperCase() + sourceType.slice(1)} ${label}`;
    };

    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs border ${getBadgeColor()}`}
      >
        {getBadgeIcon()}
        {getBadgeText()}
      </span>
    );
  };

  return (
    <>
      {/* Floating Debug Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-4 right-4 z-50 bg-orange-500 hover:bg-orange-600 text-white rounded-full p-3 shadow-lg transition-all duration-200 group"
        title="Debug Panel"
      >
        <Bug className="w-5 h-5" />
        <span className="absolute -top-2 -right-2 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center animate-pulse">
          {isTestMode ? "T" : "D"}
        </span>
      </button>

      {/* Debug Panel */}
      {isOpen && (
        <div
          ref={dialogRef}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setIsOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="debug-panel-title"
          tabIndex={-1}
        >
          <div
            className="bg-white rounded-lg shadow-xl w-[90%] max-w-4xl h-[80vh] flex flex-col"
            onClick={e => e.stopPropagation()}
            role="document"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b bg-gray-50">
              <div className="flex items-center gap-2">
                <Bug className="w-5 h-5 text-orange-500" />
                <h2 id="debug-panel-title" className="text-lg font-semibold">
                  Debug Panel - API Data Inspector
                </h2>
                <span className="text-xs bg-orange-100 text-orange-700 px-2 py-1 rounded">
                  {isTestMode ? "TEST MODE" : "DEV MODE"}
                </span>
                <span
                  className={`text-xs px-2 py-1 rounded uppercase font-medium ${
                    dataSourceInfo.environment === "dev"
                      ? "bg-blue-100 text-blue-700"
                      : dataSourceInfo.environment === "test"
                        ? "bg-yellow-100 text-yellow-700"
                        : dataSourceInfo.environment === "prod"
                          ? "bg-red-100 text-red-700"
                          : "bg-gray-100 text-gray-700"
                  }`}
                >
                  {dataSourceInfo.environment}
                </span>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 hover:bg-gray-200 rounded transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Current User Info */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                  <span className="font-semibold text-sm">Current User</span>
                </div>
                {user ? (
                  <div className="text-sm space-y-1">
                    <div>
                      ID:{" "}
                      <span className="font-mono text-blue-600">{user.id}</span>
                    </div>
                    <div>
                      Email:{" "}
                      <span className="font-mono text-blue-600">
                        {user.email}
                      </span>
                    </div>
                    <div>
                      Role:{" "}
                      <span className="font-mono text-blue-600">
                        {user.role}
                      </span>
                    </div>
                    <div>
                      NYCU ID:{" "}
                      <span className="font-mono text-blue-600">
                        {user.nycu_id || "N/A"}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="text-gray-500 text-sm">No user logged in</div>
                )}
              </div>

              {/* JWT Token Data */}
              <div className="border rounded-lg">
                <button
                  onClick={() => toggleSection("jwt")}
                  className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  <span className="font-semibold">JWT Token Data</span>
                  {expandedSections.has("jwt") ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                </button>
                {expandedSections.has("jwt") && (
                  <div className="p-4 bg-gray-50">
                    {jwtData ? (
                      <div className="font-mono text-xs overflow-x-auto">
                        {renderValue(jwtData)}
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <div className="text-gray-500">No JWT data decoded</div>
                        {token && (
                          <div className="space-y-1">
                            <div className="text-xs text-gray-600">
                              Raw Token Info:
                            </div>
                            <div className="font-mono text-xs bg-gray-100 p-2 rounded">
                              <div>Length: {token.length}</div>
                              <div>Parts: {token.split(".").length}</div>
                              <div>
                                First 100 chars: {token.substring(0, 100)}...
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Portal SSO Data */}
              <div className="border rounded-lg">
                <div className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors">
                  <div
                    className="flex items-center gap-2 flex-1 cursor-pointer"
                    onClick={() => toggleSection("portal")}
                  >
                    <span className="font-semibold">Portal SSO Data</span>
                    {getSourceBadge(dataSourceInfo.portalSource, "SSO")}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={e => {
                        e.stopPropagation();
                        fetchPortalData();
                      }}
                      disabled={isRefreshing.has("portal")}
                      className="p-1 hover:bg-gray-200 rounded transition-colors disabled:opacity-50"
                      title="Refresh Portal SSO Data"
                    >
                      <RefreshCw
                        className={`w-3 h-3 ${isRefreshing.has("portal") ? "animate-spin" : ""}`}
                      />
                    </button>
                    <div
                      className="cursor-pointer p-1"
                      onClick={() => toggleSection("portal")}
                    >
                      {expandedSections.has("portal") ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </div>
                  </div>
                </div>
                {expandedSections.has("portal") && (
                  <div className="p-4 bg-gray-50">
                    {portalData ? (
                      <div className="font-mono text-xs overflow-x-auto">
                        {renderValue(portalData)}
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <div className="text-gray-500">
                          No Portal SSO data available in JWT payload
                        </div>
                        <div className="text-xs text-gray-400 space-y-1">
                          <div>
                            • Portal data may not be included in debug mode
                          </div>
                          <div>
                            • Data source detection:{" "}
                            <span className="font-mono text-blue-600">
                              {dataSourceInfo.portalSource}
                            </span>
                          </div>
                          <div>
                            • Environment:{" "}
                            <span className="font-mono text-blue-600">
                              {dataSourceInfo.environment}
                            </span>
                          </div>
                          {dataSourceInfo.portalSource === "mock" && (
                            <div>• Using mock SSO service for development</div>
                          )}
                          {dataSourceInfo.portalSource === "real" && (
                            <div>
                              • Using real Portal JWT server:
                              portal.test.nycu.edu.tw
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Student API Data */}
              <div className="border rounded-lg">
                <div className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors">
                  <div
                    className="flex items-center gap-2 flex-1 cursor-pointer"
                    onClick={() => toggleSection("student")}
                  >
                    <span className="font-semibold">Student API Data</span>
                    {getSourceBadge(dataSourceInfo.studentApiSource, "API")}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={e => {
                        e.stopPropagation();
                        fetchStudentData();
                      }}
                      disabled={isRefreshing.has("student")}
                      className="p-1 hover:bg-gray-200 rounded transition-colors disabled:opacity-50"
                      title="Refresh Student API Data"
                    >
                      <RefreshCw
                        className={`w-3 h-3 ${isRefreshing.has("student") ? "animate-spin" : ""}`}
                      />
                    </button>
                    <div
                      className="cursor-pointer p-1"
                      onClick={() => toggleSection("student")}
                    >
                      {expandedSections.has("student") ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </div>
                  </div>
                </div>
                {expandedSections.has("student") && (
                  <div className="p-4 bg-gray-50">
                    {studentData ? (
                      <div className="space-y-4">
                        {/* Basic Student Info */}
                        <div>
                          <div className="font-semibold text-sm mb-2">基本資料</div>
                          <div className="font-mono text-xs overflow-x-auto bg-white p-2 rounded">
                            {renderValue(studentData.student || studentData)}
                          </div>
                        </div>

                        {/* Debug: Show what's in studentData */}
                        <div className="text-xs text-gray-500 bg-yellow-50 p-2 rounded">
                          Debug: semesters exists: {String(!!studentData.semesters)} |
                          length: {studentData.semesters?.length || 0} |
                          keys: {Object.keys(studentData).join(', ')}
                        </div>

                        {/* Semester Data */}
                        {studentData.semesters && studentData.semesters.length > 0 && (
                          <div>
                            <div className="font-semibold text-sm mb-2">
                              學期資料 ({studentData.semesters.length} 筆)
                            </div>
                            <div className="space-y-2">
                              {studentData.semesters.map((semester: any, index: number) => (
                                <div key={index} className="bg-white p-3 rounded border border-gray-200">
                                  <div className="font-semibold text-xs mb-2 text-blue-600">
                                    {semester.academic_year || semester.trm_year} 學年 第 {semester.term || semester.trm_term} 學期
                                  </div>
                                  <div className="font-mono text-xs overflow-x-auto">
                                    {renderValue(semester)}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <div className="text-gray-500">
                          No Student API data available in JWT payload
                        </div>
                        <div className="text-xs text-gray-400 space-y-1">
                          <div>
                            • Student data may not be included in debug mode
                          </div>
                          <div>
                            • Data source detection:{" "}
                            <span className="font-mono text-blue-600">
                              {dataSourceInfo.studentApiSource}
                            </span>
                          </div>
                          <div>
                            • Environment:{" "}
                            <span className="font-mono text-blue-600">
                              {dataSourceInfo.environment}
                            </span>
                          </div>
                          {dataSourceInfo.studentApiSource === "mock" && (
                            <div>
                              • Using mock-student-api:8080 for backdrop
                              functionality
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Environment Info */}
              <div className="border rounded-lg">
                <button
                  onClick={() => toggleSection("env")}
                  className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  <span className="font-semibold">Environment Info</span>
                  {expandedSections.has("env") ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                </button>
                {expandedSections.has("env") && (
                  <div className="p-4 bg-gray-50 font-mono text-xs space-y-2">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <div className="text-gray-600 font-semibold">
                          Environment
                        </div>
                        <div>
                          NODE_ENV:{" "}
                          <span className="text-blue-600">
                            {process.env.NODE_ENV}
                          </span>
                        </div>
                        <div>
                          Detected:{" "}
                          <span className="text-blue-600">
                            {dataSourceInfo.environment}
                          </span>
                        </div>
                        <div>
                          API URL:{" "}
                          <span className="text-blue-600">
                            {process.env.NEXT_PUBLIC_API_URL || "Not set"}
                          </span>
                        </div>
                        <div>
                          Host:{" "}
                          <span className="text-blue-600">
                            {typeof window !== "undefined"
                              ? window.location.host
                              : "N/A"}
                          </span>
                        </div>
                        <div>
                          Protocol:{" "}
                          <span className="text-blue-600">
                            {typeof window !== "undefined"
                              ? window.location.protocol
                              : "N/A"}
                          </span>
                        </div>
                      </div>
                      <div className="space-y-1">
                        <div className="text-gray-600 font-semibold">
                          Data Sources
                        </div>
                        <div>
                          Portal SSO:{" "}
                          <span className="text-blue-600">
                            {dataSourceInfo.portalSource}
                          </span>
                        </div>
                        <div>
                          Student API:{" "}
                          <span className="text-blue-600">
                            {dataSourceInfo.studentApiSource}
                          </span>
                        </div>
                        <div>
                          Debug Mode:{" "}
                          <span className="text-blue-600">
                            {jwtData?.debug_mode ? "Yes" : "No"}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="pt-2 border-t border-gray-200">
                      <div className="text-gray-600 font-semibold mb-1">
                        User Agent
                      </div>
                      <div className="text-xs text-blue-600 break-all">
                        {typeof window !== "undefined"
                          ? navigator.userAgent
                          : "N/A"}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t bg-gray-50 text-xs text-gray-600">
              <div className="flex items-center justify-between">
                <span>Debug panel active in test/development mode</span>
                <span>Last updated: {new Date().toLocaleTimeString()}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
