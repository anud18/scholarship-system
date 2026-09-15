import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { apiClient } from "@/lib/api";
import { UserPermissionManagement } from "../user-permission-management";

// The user object must be referentially stable: the component's fetch effect
// depends on `user`, so a fresh object per render would refetch forever.
const mockAuth = { user: { id: 1, role: "super_admin", name: "Super" } };
jest.mock("@/hooks/use-auth", () => ({
  useAuth: () => mockAuth,
}));

const STUDENT = {
  id: 42,
  nycu_id: "stu001",
  name: "學生甲",
  email: "stu001@nycu.edu.tw",
  role: "student",
  user_type: "student",
  status: "在學",
  created_at: "2026-01-01T00:00:00Z",
};

const ok = <T,>(data: T) => ({ success: true, message: "ok", data });

describe("UserPermissionManagement — student role changes", () => {
  let getAll: jest.SpyInstance;
  let update: jest.SpyInstance;

  beforeEach(() => {
    getAll = jest
      .spyOn(apiClient.users, "getAll")
      .mockResolvedValue(ok({ items: [STUDENT], total: 1 }) as never);
    update = jest
      .spyOn(apiClient.users, "update")
      .mockResolvedValue(ok({ ...STUDENT, role: "college" }) as never);
    jest.spyOn(apiClient.users, "getStats").mockResolvedValue(
      ok({
        total_users: 1,
        role_distribution: { student: 1 },
        user_type_distribution: {},
        status_distribution: {},
        recent_registrations: 0,
      }) as never
    );
    jest
      .spyOn(apiClient.admin, "getScholarshipPermissions")
      .mockResolvedValue(ok([]) as never);
    jest
      .spyOn(apiClient.admin, "getAllScholarshipsForPermissions")
      .mockResolvedValue(ok([]) as never);
    jest
      .spyOn(apiClient.referenceData, "getAcademies")
      .mockResolvedValue(ok([{ id: 1, code: "E", name: "電機學院" }]) as never);
    jest
      .spyOn(apiClient.referenceData, "getDepartments")
      .mockResolvedValue(ok([]) as never);
    global.fetch = jest.fn().mockResolvedValue({ ok: true }) as never;
  });

  afterEach(() => jest.restoreAllMocks());

  it("hides students by default but includes them via the 學生 filter or a search", async () => {
    render(<UserPermissionManagement />);
    await waitFor(() => expect(getAll).toHaveBeenCalled());
    expect(getAll.mock.calls[0][0].roles).not.toContain("student");

    fireEvent.change(screen.getByDisplayValue("全部管理角色"), {
      target: { value: "student" },
    });
    await waitFor(() =>
      expect(getAll).toHaveBeenLastCalledWith(
        expect.objectContaining({ roles: "student" })
      )
    );

    fireEvent.change(screen.getByDisplayValue("學生"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByPlaceholderText("姓名、信箱或 NYCU ID"), {
      target: { value: "stu001" },
    });
    await waitFor(() =>
      expect(getAll).toHaveBeenLastCalledWith(
        expect.objectContaining({
          search: "stu001",
          roles: expect.stringContaining("student"),
        })
      )
    );
  });

  it("lets a super admin promote a student to 學院", async () => {
    render(<UserPermissionManagement />);
    fireEvent.click(await screen.findByRole("button", { name: /更改角色/ }));
    await screen.findByText("編輯使用者權限");

    const roleSelect = screen.getByDisplayValue("學生");
    fireEvent.change(roleSelect, { target: { value: "college" } });
    fireEvent.change(await screen.findByDisplayValue("請選擇學院"), {
      target: { value: "E" },
    });
    fireEvent.click(screen.getByRole("button", { name: /更新權限/ }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        42,
        expect.objectContaining({ role: "college", college_code: "E" })
      )
    );
  });
});
