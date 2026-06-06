/**
 * Tests for `AdminRuleManagement` — the admin UI for managing scholarship
 * eligibility rules per academic year/semester.
 *
 * 701 LOC, previously zero tests. Renders one of the 9 untested admin
 * components called out in the production-readiness audit.
 *
 * What's pinned:
 * - Empty-state copy when no scholarship types passed in (the
 *   `scholarshipTypes.length === 0` short-circuit before any API calls).
 * - Tab list renders one tab per scholarship type.
 * - On mount, fetches available years AND rules from the API for the
 *   currently-selected type.
 * - Year fetch failure does not crash the component (`.then` chain has
 *   .catch in production code).
 *
 * Deeper interactions (create/edit/delete via the modal, copy-rules
 * dialog) are covered in their own component tests — this file focuses
 * on the data-loading boundary, which is where most prod bugs surface.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { AdminRuleManagement } from "../admin-rule-management";
import { api } from "@/lib/api";

jest.mock("../scholarship-rule-modal", () => ({
  ScholarshipRuleModal: () => null,
}));
jest.mock("../copy-rules-modal", () => ({
  CopyRulesModal: () => null,
}));
jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
jest.mock("@/hooks/use-auth", () => ({
  __esModule: true,
  useAuth: () => ({
    isAuthenticated: true,
    user: { id: 1, role: "admin", name: "Test Admin" },
    login: jest.fn(),
    logout: jest.fn(),
    isLoading: false,
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

afterEach(() => {
  jest.restoreAllMocks();
});

describe("AdminRuleManagement", () => {
  it("renders empty-state copy and short-circuits the rules fetch when scholarshipTypes is []", () => {
    jest
      .spyOn(api.admin, "getAvailableYears")
      .mockResolvedValue({ success: true, data: [114, 113, 112] } as never);
    const rulesSpy = jest
      .spyOn(api.admin, "getScholarshipRules")
      .mockResolvedValue({ success: true, data: [] } as never);

    render(<AdminRuleManagement scholarshipTypes={[]} />);
    expect(screen.getByText("尚無獎學金類型")).toBeInTheDocument();

    // Rules short-circuit: with no scholarship types there is never a
    // selected type, so the rules-loading effect never calls the API.
    // (The available-years effect, by contrast, fetches unconditionally on
    // mount — it is intentionally NOT asserted here.)
    expect(rulesSpy).not.toHaveBeenCalled();
  });

  it("renders a TabsTrigger for each scholarship type", () => {
    jest
      .spyOn(api.admin, "getAvailableYears")
      .mockResolvedValue({ success: true, data: [114, 113, 112] } as never);
    jest
      .spyOn(api.admin, "getScholarshipRules")
      .mockResolvedValue({ success: true, data: [] } as never);

    render(
      <AdminRuleManagement
        scholarshipTypes={[
          {
            id: 1,
            code: "phd",
            name: "博士獎學金",
            application_cycle: "semester",
          } as never,
          {
            id: 2,
            code: "undergrad",
            name: "學士新生",
            application_cycle: "yearly",
          } as never,
        ]}
      />
    );
    expect(screen.getByRole("tab", { name: "博士獎學金" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "學士新生" })).toBeInTheDocument();
  });

  it("fetches available years from the API on mount", async () => {
    const yearsSpy = jest
      .spyOn(api.admin, "getAvailableYears")
      .mockResolvedValue({ success: true, data: [114, 113, 112] } as never);
    jest
      .spyOn(api.admin, "getScholarshipRules")
      .mockResolvedValue({ success: true, data: [] } as never);

    render(
      <AdminRuleManagement
        scholarshipTypes={[
          {
            id: 1,
            code: "phd",
            name: "博士獎學金",
            application_cycle: "semester",
          } as never,
        ]}
      />
    );

    await waitFor(() => {
      expect(yearsSpy).toHaveBeenCalled();
    });
  });

  it("fetches rules for the active scholarship type when one is selected", async () => {
    jest
      .spyOn(api.admin, "getAvailableYears")
      .mockResolvedValue({ success: true, data: [114, 113, 112] } as never);
    const rulesSpy = jest
      .spyOn(api.admin, "getScholarshipRules")
      .mockResolvedValue({
        success: true,
        data: [
          {
            id: 99,
            name: "GPA 必須 3.5 以上",
            description: "min GPA threshold",
          },
        ],
      } as never);

    render(
      <AdminRuleManagement
        scholarshipTypes={[
          {
            id: 1,
            code: "phd",
            name: "博士獎學金",
            application_cycle: "semester",
          } as never,
        ]}
      />
    );

    // Wait for the auto-selection + fetch to settle.
    await waitFor(() => {
      expect(rulesSpy).toHaveBeenCalled();
    });
  });

  it("does not crash if the years endpoint rejects", async () => {
    // The "years" API failure used to silently break the year selector;
    // pin that the component still renders the tab list and doesn't
    // unmount on the error.
    const yearsSpy = jest
      .spyOn(api.admin, "getAvailableYears")
      .mockRejectedValue(new Error("network down"));
    jest
      .spyOn(api.admin, "getScholarshipRules")
      .mockResolvedValue({ success: true, data: [] } as never);

    render(
      <AdminRuleManagement
        scholarshipTypes={[
          {
            id: 1,
            code: "phd",
            name: "博士獎學金",
            application_cycle: "semester",
          } as never,
        ]}
      />
    );

    // Tabs render regardless of the years-fetch outcome.
    expect(screen.getByRole("tab", { name: "博士獎學金" })).toBeInTheDocument();

    // The rejection must have been awaited (queued .then in production code).
    await waitFor(() => {
      expect(yearsSpy).toHaveBeenCalled();
    });
  });

  it("does not crash if the rules endpoint returns an unsuccessful response", async () => {
    // Pin the soft-failure branch: production code maps a non-success
    // response to setRules([]), not an exception bubbling out.
    jest
      .spyOn(api.admin, "getAvailableYears")
      .mockResolvedValue({ success: true, data: [114, 113, 112] } as never);
    const rulesSpy = jest
      .spyOn(api.admin, "getScholarshipRules")
      .mockResolvedValue({
        success: false,
        message: "no rules configured",
      } as never);

    render(
      <AdminRuleManagement
        scholarshipTypes={[
          {
            id: 1,
            code: "phd",
            name: "博士獎學金",
            application_cycle: "semester",
          } as never,
        ]}
      />
    );

    await waitFor(() => {
      expect(rulesSpy).toHaveBeenCalled();
    });

    // Tab list still renders — nothing crashed.
    expect(screen.getByRole("tab", { name: "博士獎學金" })).toBeInTheDocument();
  });
});
