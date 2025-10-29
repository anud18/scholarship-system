"use client";

import React, { createContext, useContext, useState, useCallback } from "react";

interface AdminManagementContextType {
  // Active tab management
  activeTab: string;
  setActiveTab: (tab: string) => void;

  // User permissions (will be populated from useAuth)
  userRole: string | null;
  canManageScholarships: boolean;
  canManageUsers: boolean;
  canManageSystem: boolean;

  // Shared caches
  scholarshipTypes: any[];
  setScholarshipTypes: (types: any[]) => void;

  // Common filters that might be shared
  selectedAcademicYear: number;
  setSelectedAcademicYear: (year: number) => void;

  selectedSemester: string | null;
  setSelectedSemester: (semester: string | null) => void;

  // Loading states for shared data
  isLoadingShared: boolean;
  setIsLoadingShared: (loading: boolean) => void;
}

const AdminManagementContext = createContext<
  AdminManagementContextType | undefined
>(undefined);

export function AdminManagementProvider({
  children,
  userRole = null,
}: {
  children: React.ReactNode;
  userRole?: string | null;
}) {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [scholarshipTypes, setScholarshipTypes] = useState<any[]>([]);
  const [selectedAcademicYear, setSelectedAcademicYear] = useState(114);
  const [selectedSemester, setSelectedSemester] = useState<string | null>(null);
  const [isLoadingShared, setIsLoadingShared] = useState(false);

  // Derive permissions from user role
  const canManageScholarships = ["admin", "super_admin"].includes(
    userRole || ""
  );
  const canManageUsers = ["super_admin"].includes(userRole || "");
  const canManageSystem = ["super_admin"].includes(userRole || "");

  const value: AdminManagementContextType = {
    activeTab,
    setActiveTab,
    userRole,
    canManageScholarships,
    canManageUsers,
    canManageSystem,
    scholarshipTypes,
    setScholarshipTypes,
    selectedAcademicYear,
    setSelectedAcademicYear,
    selectedSemester,
    setSelectedSemester,
    isLoadingShared,
    setIsLoadingShared,
  };

  return (
    <AdminManagementContext.Provider value={value}>
      {children}
    </AdminManagementContext.Provider>
  );
}

export function useAdminManagement() {
  const context = useContext(AdminManagementContext);
  if (context === undefined) {
    throw new Error(
      "useAdminManagement must be used within an AdminManagementProvider"
    );
  }
  return context;
}
