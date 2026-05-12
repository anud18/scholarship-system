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

const mockGetAvailableYears = jest.fn();
const mockGetScholarshipRules = jest.fn();

jest.mock("@/lib/api", () => ({
  __esModule: true,
  api: {
    admin: {
      getAvailableYears: (...args: unknown[]) => mockGetAvailableYears(...args),
      getScholarshipRules: (...args: unknown[]) => mockGetScholarshipRules(...args),
      deleteScholarshipRule: jest.fn(),
      createScholarshipRule: jest.fn(),
      updateScholarshipRule: jest.fn(),
      copyRulesBetweenPeriods: jest.fn(),
    },
  },
  ScholarshipType: {},
  ScholarshipRule: {},
}));

jest.mock("../scholarship-rule-modal", () => ({
  ScholarshipRuleModal: () => null,
}));
jest.mock("../copy-rules-modal", () => ({
  CopyRulesModal: () => null,
}));
jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

beforeEach(() => {
  mockGetAvailableYears.mockResolvedValue({
    success: true,
    data: { years: [114, 113, 112] },
  });
  mockGetScholarshipRules.mockResolvedValue({
    success: true,
    data: [],
  });
});

describe("AdminRuleManagement", () => {
  it("renders empty-state copy and short-circuits API calls when scholarshipTypes is []", () => {
    render(<AdminRuleManagement scholarshipTypes={[]} />);
    expect(screen.getByText("尚無獎學金類型")).toBeInTheDocument();

    // Short-circuit: no API calls fire when there's nothing to manage.
    expect(mockGetAvailableYears).not.toHaveBeenCalled();
    expect(mockGetScholarshipRules).not.toHaveBeenCalled();
  });

  it("renders a TabsTrigger for each scholarship type", () => {
    render(
      <AdminRuleManagement
        scholarshipTypes={[
          { id: 1, code: "phd", name: "博士獎學金", application_cycle: "semester" } as never,
          { id: 2, code: "undergrad", name: "學士新生", application_cycle: "yearly" } as never,
        ]}
      />,
    );
    expect(screen.getByRole("tab", { name: "博士獎學金" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "學士新生" })).toBeInTheDocument();
  });

  it("fetches available years from the API on mount", async () => {
    render(
      <AdminRuleManagement
        scholarshipTypes={[
          { id: 1, code: "phd", name: "博士獎學金", application_cycle: "semester" } as never,
        ]}
      />,
    );

    await waitFor(() => {
      expect(mockGetAvailableYears).toHaveBeenCalled();
    });
  });

  it("fetches rules for the active scholarship type when one is selected", async () => {
    mockGetScholarshipRules.mockResolvedValue({
      success: true,
      data: [
        { id: 99, name: "GPA 必須 3.5 以上", description: "min GPA threshold" },
      ],
    });

    render(
      <AdminRuleManagement
        scholarshipTypes={[
          { id: 1, code: "phd", name: "博士獎學金", application_cycle: "semester" } as never,
        ]}
      />,
    );

    // Wait for the auto-selection + fetch to settle.
    await waitFor(() => {
      expect(mockGetScholarshipRules).toHaveBeenCalled();
    });
  });

  it("does not crash if the years endpoint rejects", async () => {
    // The "years" API failure used to silently break the year selector;
    // pin that the component still renders the tab list and doesn't
    // unmount on the error.
    mockGetAvailableYears.mockRejectedValueOnce(new Error("network down"));

    render(
      <AdminRuleManagement
        scholarshipTypes={[
          { id: 1, code: "phd", name: "博士獎學金", application_cycle: "semester" } as never,
        ]}
      />,
    );

    // Tabs render regardless of the years-fetch outcome.
    expect(screen.getByRole("tab", { name: "博士獎學金" })).toBeInTheDocument();

    // The rejection must have been awaited (queued .then in production code).
    await waitFor(() => {
      expect(mockGetAvailableYears).toHaveBeenCalled();
    });
  });

  it("does not crash if the rules endpoint returns an unsuccessful response", async () => {
    // Pin the soft-failure branch: production code maps a non-success
    // response to setRules([]), not an exception bubbling out.
    mockGetScholarshipRules.mockResolvedValue({
      success: false,
      message: "no rules configured",
    } as never);

    render(
      <AdminRuleManagement
        scholarshipTypes={[
          { id: 1, code: "phd", name: "博士獎學金", application_cycle: "semester" } as never,
        ]}
      />,
    );

    await waitFor(() => {
      expect(mockGetScholarshipRules).toHaveBeenCalled();
    });

    // Tab list still renders — nothing crashed.
    expect(screen.getByRole("tab", { name: "博士獎學金" })).toBeInTheDocument();
  });
});
