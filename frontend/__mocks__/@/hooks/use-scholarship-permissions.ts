// Mock implementation for use-scholarship-permissions
export const useScholarshipPermissions = () => ({
  canRead: true,
  canWrite: true,
  canDelete: false,
  canApprove: false,
  canReject: false,
  userRole: "admin",
  permissions: {
    scholarships: {
      create: true,
      read: true,
      update: true,
      delete: false,
    },
    applications: {
      create: true,
      read: true,
      update: true,
      delete: false,
      approve: false,
      reject: false,
    },
  },
});
