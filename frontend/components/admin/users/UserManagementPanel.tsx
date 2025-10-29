"use client";

import { UserPermissionManagement } from "@/components/user-permission-management";

export function UserManagementPanel() {
  return (
    <div className="space-y-4">
      <UserPermissionManagement />
    </div>
  );
}
