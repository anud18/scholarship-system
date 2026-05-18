import { useState, useEffect, useCallback } from "react";
import {
  apiClient,
  DashboardStats,
  Application,
  NotificationResponse,
  ScholarshipStats,
  SubTypeStats,
} from "@/lib/api";
import { logger } from "@/lib/utils/logger";
import { useAuth } from "@/hooks/use-auth";
import { useScholarshipPermissions } from "./use-scholarship-permissions";

export function useAdminDashboard() {
  const { user, isAuthenticated } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentApplications, setRecentApplications] = useState<Application[]>(
    []
  );
  const [systemAnnouncements, setSystemAnnouncements] = useState<
    NotificationResponse[]
  >([]);
  const [allApplications, setAllApplications] = useState<Application[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isStatsLoading, setIsStatsLoading] = useState(false);
  const [isRecentLoading, setIsRecentLoading] = useState(false);
  const [isAnnouncementsLoading, setIsAnnouncementsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({
    page: 1,
    size: 20,
    total: 0,
  });

  const fetchDashboardStats = useCallback(async () => {
    // Only fetch if user is authenticated and has admin privileges
    if (
      !isAuthenticated ||
      !user ||
      (user.role !== "admin" && user.role !== "super_admin")
    ) {
      return;
    }

    try {
      setIsStatsLoading(true);
      setError(null);

      const response = await apiClient.admin.getDashboardStats();

      if (response.success && response.data) {
        setStats(response.data);
      } else {
        throw new Error(response.message || "Failed to fetch dashboard stats");
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch dashboard stats"
      );
    } finally {
      setIsStatsLoading(false);
    }
  }, [isAuthenticated, user]);

  const fetchRecentApplications = useCallback(async () => {
    // Only fetch if user is authenticated and has admin privileges
    if (
      !isAuthenticated ||
      !user ||
      (user.role !== "admin" && user.role !== "super_admin")
    ) {
      logger.warn(
        "fetchRecentApplications: user not authenticated or insufficient privileges",
        {
          isAuthenticated,
          userId: user?.id,
          role: user?.role,
        }
      );
      return;
    }

    try {
      setIsRecentLoading(true);
      setError(null);

      logger.debug("Fetching recent applications");
      const response = await apiClient.admin.getRecentApplications(5);
      logger.debug("Recent applications response received", {
        success: response.success,
        count: response.data?.length ?? 0,
      });

      if (response.success && response.data) {
        setRecentApplications(response.data as Application[]);
      } else {
        const errorMsg =
          response.message || "Failed to fetch recent applications";
        logger.error("Recent applications fetch failed", {
          errorMsg,
          success: response.success,
        });
        throw new Error(errorMsg);
      }
    } catch (err) {
      const errorMsg =
        err instanceof Error
          ? err.message
          : "Failed to fetch recent applications";
      logger.error("Error fetching recent applications", { err });
      setError(errorMsg);
    } finally {
      setIsRecentLoading(false);
    }
  }, [isAuthenticated, user]);

  const fetchSystemAnnouncements = useCallback(async () => {
    // Only fetch if user is authenticated and has admin privileges
    if (
      !isAuthenticated ||
      !user ||
      (user.role !== "admin" && user.role !== "super_admin")
    ) {
      return;
    }

    try {
      setIsAnnouncementsLoading(true);
      setError(null);

      const response = await apiClient.admin.getSystemAnnouncements(5);

      if (response.success && response.data) {
        setSystemAnnouncements(response.data as NotificationResponse[]);
      } else {
        throw new Error(
          response.message || "Failed to fetch system announcements"
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to fetch system announcements"
      );
    } finally {
      setIsAnnouncementsLoading(false);
    }
  }, [isAuthenticated, user]);

  const fetchAllApplications = useCallback(
    async (page = 1, size = 20, status?: string) => {
      // Only fetch if user is authenticated and has admin privileges
      if (
        !isAuthenticated ||
        !user ||
        (user.role !== "admin" && user.role !== "super_admin")
      ) {
        return;
      }

      try {
        setIsLoading(true);
        setError(null);

        const response = await apiClient.admin.getAllApplications(
          page,
          size,
          status
        );

        if (response.success && response.data) {
          setAllApplications(response.data.items as Application[]);
          setPagination({
            page: response.data.page,
            size: response.data.size,
            total: response.data.total,
          });
        } else {
          throw new Error(response.message || "Failed to fetch applications");
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to fetch applications"
        );
      } finally {
        setIsLoading(false);
      }
    },
    [isAuthenticated, user]
  );

  const updateApplicationStatus = useCallback(
    async (applicationId: number, status: string, reviewNotes?: string) => {
      try {
        setError(null);

        const response = await apiClient.admin.updateApplicationStatus(
          applicationId,
          status,
          reviewNotes
        );

        if (response.success && response.data) {
          // Update the application in the list
          setAllApplications(prev =>
            prev.map(app => (app.id === applicationId ? response.data! as Application : app))
          );

          // Refresh stats to reflect the change
          await fetchDashboardStats();

          return response.data;
        } else {
          throw new Error(
            response.message || "Failed to update application status"
          );
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to update application status"
        );
        throw err;
      }
    },
    [fetchDashboardStats]
  );

  // Fetch initial data on mount
  useEffect(() => {
    if (
      isAuthenticated &&
      user &&
      (user.role === "admin" || user.role === "super_admin")
    ) {
      fetchDashboardStats();
      fetchRecentApplications();
      fetchSystemAnnouncements();
      fetchAllApplications();
    }
  }, [
    isAuthenticated,
    user,
    fetchDashboardStats,
    fetchRecentApplications,
    fetchSystemAnnouncements,
    fetchAllApplications,
  ]);

  return {
    stats,
    recentApplications,
    systemAnnouncements,
    allApplications,
    pagination,
    isLoading,
    isStatsLoading,
    isRecentLoading,
    isAnnouncementsLoading,
    error,
    fetchDashboardStats,
    fetchRecentApplications,
    fetchSystemAnnouncements,
    fetchAllApplications,
    updateApplicationStatus,
  };
}

export function useCollegeApplications() {
  const { user, isAuthenticated } = useAuth();
  const [applications, setApplications] = useState<Application[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCollegeApplications = useCallback(
    async (
      academicYear?: number,
      semester?: string,
      scholarshipType?: string
    ) => {
      // Only fetch if user is authenticated and has college privileges
      if (!isAuthenticated || !user || user.role !== "college") {
        return;
      }

      try {
        setIsLoading(true);
        setError(null);

        // Build query parameters
        const params = new URLSearchParams();
        if (academicYear)
          params.append("academic_year", academicYear.toString());
        if (semester) params.append("semester", semester);
        if (scholarshipType) params.append("scholarship_type", scholarshipType);

        const queryString = params.toString();

        // Use the new college-specific endpoint
        const response =
          await apiClient.college.getApplicationsForReview(queryString);

        if (response.success && response.data) {
          // Transform data to ensure consistent field mapping
          const transformedApplications = response.data.map(app => {
            // Loose typing for fields not on the canonical Application
            // type (the college-review endpoint includes a denormalized
            // `student_info` block plus already-flattened student_name /
            // student_id strings). We narrow only the read fields.
            const a = app as Application & {
              student_info?: {
                display_name?: string;
                student_id_masked?: string;
              };
            };
            return {
              ...a,
              student_name:
                a.student_name ||
                a.student_info?.display_name ||
                "未提供姓名",
              student_id:
                a.student_id || a.student_info?.student_id_masked || "N/A",
            };
          });
          setApplications(transformedApplications);
        } else {
          throw new Error(
            response.message || "Failed to fetch college applications"
          );
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to fetch college applications"
        );
      } finally {
        setIsLoading(false);
      }
    },
    [isAuthenticated, user]
  );

  const updateApplicationStatus = useCallback(
    async (applicationId: number, status: string, reviewNotes?: string) => {
      try {
        setError(null);

        // Step 1: Get available sub-types for this application
        const subTypesResponse = await apiClient.college.getSubTypes(applicationId);

        if (!subTypesResponse.success || !subTypesResponse.data) {
          throw new Error("Failed to fetch application sub-types");
        }

        const subTypes = subTypesResponse.data;

        // Step 2: Create review items for all sub-types
        const recommendation = status === 'approved' ? ('approve' as const) : ('reject' as const);
        const items = subTypes.map((subType: string) => ({
          sub_type_code: subType,
          recommendation: recommendation,
          comments: reviewNotes || (recommendation === 'approve' ? '同意' : '駁回'),
        }));

        // Step 3: Submit unified review using submitReview API
        const response = await apiClient.college.submitReview(
          applicationId,
          { items }
        );

        if (response.success && response.data) {
          // Update the application in the list
          setApplications(prev =>
            prev.map(app => (app.id === applicationId ? response.data! : app))
          );

          return response.data;
        } else {
          throw new Error(
            response.message || "Failed to update application status"
          );
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to update application status"
        );
        throw err;
      }
    },
    []
  );

  // Fetch initial data on mount
  useEffect(() => {
    if (isAuthenticated && user && user.role === "college") {
      fetchCollegeApplications();
    }
  }, [isAuthenticated, user, fetchCollegeApplications]);

  return {
    applications,
    isLoading,
    error,
    fetchCollegeApplications,
    updateApplicationStatus,
  };
}

export function useScholarshipSpecificApplications() {
  const { user, isAuthenticated } = useAuth();
  const [applicationsByType, setApplicationsByType] = useState<
    Record<string, Application[]>
  >({});
  const [scholarshipTypes, setScholarshipTypes] = useState<string[]>([]);
  const [scholarshipStats, setScholarshipStats] = useState<Record<string, any>>(
    {}
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Get user's scholarship permissions
  const { filterScholarshipsByPermission } = useScholarshipPermissions();

  const fetchScholarshipTypes = useCallback(async () => {
    if (
      !isAuthenticated ||
      !user ||
      !["admin", "super_admin", "college", "professor"].includes(user.role)
    ) {
      return;
    }

    try {
      const response = await apiClient.admin.getScholarshipStats();
      if (response.success && response.data) {
        const types = Object.keys(response.data);

        // Filter scholarship types based on user permissions
        // Super admin has access to all scholarships
        let filteredTypes = types;
        if (user.role === "admin" || user.role === "college") {
          // Create objects with both id and code for filtering
          const scholarshipObjects = types.map(type => ({
            id: (response.data![type] as { id: number }).id, // Use the actual scholarship ID
            code: type, // Keep the code for reference
          }));

          const filteredObjects =
            filterScholarshipsByPermission(scholarshipObjects);
          filteredTypes = filteredObjects.map(obj => obj.code); // Return the codes
        }

        setScholarshipTypes(filteredTypes);
        // Filter stats to only include permitted scholarships
        const filteredStats: Record<string, any> = {};
        filteredTypes.forEach(type => {
          if (response.data![type]) {
            filteredStats[type] = response.data![type];
          }
        });
        setScholarshipStats(filteredStats);
        return filteredTypes;
      }
      return [];
    } catch (err) {
      logger.error("Failed to fetch scholarship types", { err });
      return [];
    }
  }, [isAuthenticated, user, filterScholarshipsByPermission]);

  const fetchApplicationsByType = useCallback(async () => {
    // Only fetch if user is authenticated and has staff privileges (admin, super_admin, college, or professor)
    if (
      !isAuthenticated ||
      !user ||
      !["admin", "super_admin", "college", "professor"].includes(user.role)
    ) {
      logger.debug(
        "fetchApplicationsByType: user not authenticated or insufficient privileges"
      );
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      logger.debug("Fetching scholarship types");
      // First get scholarship types from backend (already filtered by permissions)
      const types = await fetchScholarshipTypes();
      logger.debug("Scholarship types received", { count: types?.length ?? 0 });

      if (!types || types.length === 0) {
        logger.debug("No scholarship types found, clearing applications");
        setApplicationsByType({});
        return;
      }

      const applications: Record<string, Application[]> = {};

      // Fetch applications for each scholarship type
      for (const type of types) {
        try {
          logger.debug("Fetching applications for scholarship type", { type });
          const response =
            await apiClient.admin.getApplicationsByScholarship(type);

          if (response.success && response.data) {
            applications[type] = response.data as Application[];
            logger.debug("Applications fetched for type", {
              type,
              count: response.data.length,
            });
          } else {
            applications[type] = [];
            logger.debug("No applications found for type", { type });
          }
        } catch (typeError) {
          logger.error("Failed to fetch applications for type", {
            type,
            typeError,
          });
          applications[type] = [];
        }
      }

      logger.debug("Final applications-by-type tally", {
        typeCount: Object.keys(applications).length,
      });
      setApplicationsByType(applications);
    } catch (err) {
      setError("Failed to fetch scholarship-specific applications");
      logger.error("Error fetching scholarship-specific applications", { err });
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, user, fetchScholarshipTypes]);

  const updateApplicationStatus = useCallback(
    async (applicationId: number, status: string, comments?: string) => {
      if (!user || !["admin", "super_admin"].includes(user.role)) {
        throw new Error("Insufficient permissions");
      }

      try {
        const response = await apiClient.admin.updateApplicationStatus(
          applicationId,
          status,
          comments
        );

        if (response.success) {
          // Refresh data after successful update
          await fetchApplicationsByType();
          return response.data;
        } else {
          throw new Error(
            response.message || "Failed to update application status"
          );
        }
      } catch (error) {
        logger.error("Failed to update application status", { error });
        throw error;
      }
    },
    [user, fetchApplicationsByType]
  );

  useEffect(() => {
    fetchApplicationsByType();
  }, [fetchApplicationsByType]);

  return {
    applicationsByType,
    scholarshipTypes,
    scholarshipStats,
    isLoading,
    error,
    refetch: fetchApplicationsByType,
    updateApplicationStatus,
  };
}

export function useScholarshipReview() {
  const { user, isAuthenticated } = useAuth();
  const [scholarshipStats, setScholarshipStats] = useState<
    Record<string, ScholarshipStats>
  >({});
  const [applicationsByScholarship, setApplicationsByScholarship] = useState<
    Record<string, Application[]>
  >({});
  const [subTypeStats, setSubTypeStats] = useState<
    Record<string, SubTypeStats[]>
  >({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchScholarshipStats = useCallback(async () => {
    if (
      !isAuthenticated ||
      !user ||
      (user.role !== "admin" && user.role !== "super_admin")
    ) {
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      const response = await apiClient.admin.getScholarshipStats();

      if (response.success && response.data) {
        setScholarshipStats(response.data as Record<string, ScholarshipStats>);
      } else {
        throw new Error(
          response.message || "Failed to fetch scholarship stats"
        );
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch scholarship stats"
      );
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, user]);

  const fetchApplicationsByScholarship = useCallback(
    async (scholarshipCode: string, subType?: string, status?: string) => {
      if (
        !isAuthenticated ||
        !user ||
        (user.role !== "admin" && user.role !== "super_admin")
      ) {
        return;
      }

      try {
        setError(null);

        const response = await apiClient.admin.getApplicationsByScholarship(
          scholarshipCode,
          subType,
          status
        );

        if (response.success && response.data) {
          setApplicationsByScholarship(prev => ({
            ...prev,
            [scholarshipCode]: (response.data as Application[]) || [],
          }));
        } else {
          throw new Error(response.message || "Failed to fetch applications");
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to fetch applications"
        );
      }
    },
    [isAuthenticated, user]
  );

  const fetchSubTypeStats = useCallback(
    async (scholarshipCode: string) => {
      if (
        !isAuthenticated ||
        !user ||
        (user.role !== "admin" && user.role !== "super_admin")
      ) {
        return;
      }

      try {
        setError(null);

        const response =
          await apiClient.admin.getScholarshipSubTypes(scholarshipCode);

        if (response.success && response.data) {
          setSubTypeStats(prev => ({
            ...prev,
            [scholarshipCode]: (response.data as SubTypeStats[]) || [],
          }));
        } else {
          throw new Error(response.message || "Failed to fetch sub-type stats");
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to fetch sub-type stats"
        );
      }
    },
    [isAuthenticated, user]
  );

  const updateApplicationStatus = useCallback(
    async (applicationId: number, status: string, reviewNotes?: string) => {
      if (!user || (user.role !== "admin" && user.role !== "super_admin")) {
        throw new Error("Insufficient permissions");
      }

      try {
        const response = await apiClient.admin.updateApplicationStatus(
          applicationId,
          status,
          reviewNotes
        );

        if (response.success && response.data) {
          // Refresh scholarship stats after update
          await fetchScholarshipStats();
          return response.data;
        } else {
          throw new Error(
            response.message || "Failed to update application status"
          );
        }
      } catch (error) {
        logger.error("Failed to update application status", { error });
        throw error;
      }
    },
    [user, fetchScholarshipStats]
  );

  useEffect(() => {
    fetchScholarshipStats();
  }, [fetchScholarshipStats]);

  return {
    scholarshipStats,
    applicationsByScholarship,
    subTypeStats,
    isLoading,
    error,
    fetchScholarshipStats,
    fetchApplicationsByScholarship,
    fetchSubTypeStats,
    updateApplicationStatus,
  };
}
