/**
 * Tests for `AdminManagementInterface` — the system-management hub.
 *
 * 3928 LOC, previously zero tests. Sixth in the 9-untested-admin-components
 * series. With this commit, all 6 large admin components called out in the
 * audit have test coverage.
 *
 * Scope: the two authorization-guard branches that gate access to the
 * entire management UI. These are the highest-value regression targets
 * because a bug in either branch would expose the management surface
 * (or hide it from the right user) — both classes of bug are security-
 * adjacent and silent in development.
 *
 * What's pinned:
 * - Unauthenticated render: `user=null` ⇒ "需要登入" guard with login CTA.
 * - Wrong-role render: `user.role` outside {"admin","super_admin"} ⇒
 *   "權限不足" guard.
 * - Super-admin gets past the role guard (component starts trying to
 *   render the management surface, NOT the guard copy).
 *
 * Deeper interactions (workflow management, email templates, scheduled
 * emails, historical applications, announcements, etc.) are intentionally
 * out of scope — each is a dedicated test surface.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { AdminManagementInterface } from "../admin-management-interface";

// Heavy sub-components: stub to null so they don't pull deps when the
// authorized render path reaches them.
jest.mock("@/components/admin-configuration-management", () => ({
  AdminConfigurationManagement: () => null,
}));
jest.mock("@/components/admin-rule-management", () => ({
  AdminRuleManagement: () => null,
}));
jest.mock("@/components/email-automation-management", () => ({
  EmailAutomationManagement: () => null,
}));
jest.mock("@/components/email-history-table", () => ({
  EmailHistoryTable: () => null,
}));
jest.mock("@/components/email-test-mode-panel", () => ({
  EmailTestModePanel: () => null,
}));
jest.mock("@/components/quota-management", () => ({
  QuotaManagement: () => null,
}));
jest.mock("@/components/scheduled-emails-table", () => ({
  ScheduledEmailsTable: () => null,
}));
jest.mock("@/components/ScholarshipWorkflowMermaid", () => ({
  ScholarshipWorkflowMermaid: () => null,
}));
jest.mock("@/components/system-configuration-management", () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock("@/components/user-edit-modal", () => ({
  UserEditModal: () => null,
}));
jest.mock("@/components/user-permission-management", () => ({
  UserPermissionManagement: () => null,
}));

// API client: every call returns a resolved permissive response so the
// component's many useEffect data loads don't reject.
jest.mock("@/lib/api", () => {
  const ok = jest.fn().mockResolvedValue({ success: true, data: [] });
  return {
    __esModule: true,
    default: new Proxy(
      {},
      {
        get: () =>
          new Proxy(
            {},
            {
              get: () => ok,
            },
          ),
      },
    ),
  };
});

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

describe("AdminManagementInterface", () => {
  it("renders the '需要登入' guard when user is null", () => {
    render(<AdminManagementInterface user={null as never} />);
    expect(screen.getByText("需要登入")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "前往登入" })).toBeInTheDocument();
  });

  it("renders the '權限不足' guard for student role", () => {
    const studentUser = {
      id: 1,
      nycu_id: "stu1",
      role: "student",
      name: "Test Student",
    };
    render(<AdminManagementInterface user={studentUser as never} />);
    expect(screen.getByText("權限不足")).toBeInTheDocument();
  });

  it("renders the '權限不足' guard for college role", () => {
    const collegeUser = {
      id: 2,
      nycu_id: "col1",
      role: "college",
      name: "Test College",
    };
    render(<AdminManagementInterface user={collegeUser as never} />);
    expect(screen.getByText("權限不足")).toBeInTheDocument();
  });

  it("renders the '權限不足' guard for professor role", () => {
    const professorUser = {
      id: 3,
      nycu_id: "prof1",
      role: "professor",
      name: "Test Professor",
    };
    render(<AdminManagementInterface user={professorUser as never} />);
    expect(screen.getByText("權限不足")).toBeInTheDocument();
  });

  it("admin role passes the auth guard — management surface starts rendering", () => {
    const adminUser = {
      id: 100,
      nycu_id: "admin1",
      role: "admin",
      name: "Test Admin",
    };
    render(<AdminManagementInterface user={adminUser as never} />);
    // Reached the authorized render: heading from the management page
    // is visible, NOT the role-guard copy.
    expect(screen.getByText("系統管理")).toBeInTheDocument();
    expect(screen.queryByText("權限不足")).not.toBeInTheDocument();
    expect(screen.queryByText("需要登入")).not.toBeInTheDocument();
  });

  it("super_admin role passes the auth guard — management surface starts rendering", () => {
    const superUser = {
      id: 101,
      nycu_id: "super1",
      role: "super_admin",
      name: "Super",
    };
    render(<AdminManagementInterface user={superUser as never} />);
    expect(screen.getByText("系統管理")).toBeInTheDocument();
    expect(screen.queryByText("權限不足")).not.toBeInTheDocument();
  });
});
