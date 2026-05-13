/**
 * Tests for `lib/utils.ts` — `formatDateTime` + `getStatusBadgeVariant`.
 *
 * The existing utils.test.ts covers `cn` only. These two helpers are
 * surface-critical:
 * - `formatDateTime` runs on every admin dashboard row (created/updated
 *   timestamps). A bug here either crashes the row render or shows
 *   'Invalid Date' to admin reviewers.
 * - `getStatusBadgeVariant` colors every application-status badge across
 *   the dashboard. Wrong variant → wrong visual signal (e.g., a rejected
 *   app showing in green) which misleads admin triage.
 *
 * 17 cases.
 */
import { formatDateTime, getStatusBadgeVariant } from "../utils";

// ─── formatDateTime ──────────────────────────────────────────────────

describe("formatDateTime", () => {
  it("returns '-' for null", () => {
    /** Optional date columns are common — null is the no-op signal. */
    expect(formatDateTime(null)).toBe("-");
  });

  it("returns '-' for undefined", () => {
    expect(formatDateTime(undefined)).toBe("-");
  });

  it("returns '-' for empty string", () => {
    expect(formatDateTime("")).toBe("-");
  });

  it("returns '-' for invalid date string", () => {
    /** new Date('xyz') produces an Invalid Date object; isNaN guard
     * catches it and returns the placeholder instead of 'Invalid Date'. */
    expect(formatDateTime("not-a-date")).toBe("-");
    expect(formatDateTime("2025-13-99")).toBe("-");
  });

  it("formats valid ISO timestamp using zh-TW locale", () => {
    /** Intl.DateTimeFormat('zh-TW') uses Western year (NOT ROC year)
     * — pin so a 2025 date stays '2025/03/15' not '114/03/15'. */
    const result = formatDateTime("2025-03-15T14:30:45Z");
    expect(result).toMatch(/2025/);
    expect(result).toMatch(/03/);
    expect(result).toMatch(/15/);
  });

  it("uses 24-hour clock (hour12: false)", () => {
    /** Pin 24-hour — admins are used to it; switching to 12-hour would
     * make 14:00 show as '02:00 PM' which is visually distracting in
     * the dense table layout. */
    const result = formatDateTime("2025-03-15T14:30:45Z");
    expect(result).not.toMatch(/AM|PM/i);
  });
});

// ─── getStatusBadgeVariant ───────────────────────────────────────────

describe("getStatusBadgeVariant", () => {
  // Success states → 'default' (the visually-prominent variant)
  describe("success states return 'default'", () => {
    it("completed", () => {
      expect(getStatusBadgeVariant("completed")).toBe("default");
    });
    it("active", () => {
      expect(getStatusBadgeVariant("active")).toBe("default");
    });
    it("approved", () => {
      expect(getStatusBadgeVariant("approved")).toBe("default");
    });
    it("verified", () => {
      expect(getStatusBadgeVariant("verified")).toBe("default");
    });
    it("locked", () => {
      expect(getStatusBadgeVariant("locked")).toBe("default");
    });
  });

  // Partial state → 'outline' (special-cased between success and pending)
  it("partial_approved returns 'outline' (special case)", () => {
    /** Partial approval is its own visual signal — admin triage needs to
     * distinguish 'fully approved' (default) from 'partially approved'
     * (outline, less prominent). */
    expect(getStatusBadgeVariant("partial_approved")).toBe("outline");
  });

  // Pending/warning → 'secondary'
  describe("pending/warning states return 'secondary'", () => {
    it("draft, pending, processing, paused, under_review", () => {
      for (const s of [
        "draft",
        "pending",
        "processing",
        "paused",
        "under_review",
      ]) {
        expect(getStatusBadgeVariant(s)).toBe("secondary");
      }
    });
  });

  // Error/failed → 'destructive' (red, attention-grabbing)
  describe("error states return 'destructive'", () => {
    it("failed, rejected, error, cancelled, disabled", () => {
      for (const s of ["failed", "rejected", "error", "cancelled", "disabled"]) {
        expect(getStatusBadgeVariant(s)).toBe("destructive");
      }
    });
  });

  it("unknown status returns 'outline' (fallback)", () => {
    /** Catch-all for new statuses added to the backend that the frontend
     * hasn't styled yet — outline is the neutral default. */
    expect(getStatusBadgeVariant("brand_new_status")).toBe("outline");
  });

  it("is case-insensitive", () => {
    /** Inputs may come from API in mixed case (esp. legacy endpoints).
     * Pin lowercase normalization so 'Approved'/'APPROVED' all work. */
    expect(getStatusBadgeVariant("APPROVED")).toBe("default");
    expect(getStatusBadgeVariant("Rejected")).toBe("destructive");
    expect(getStatusBadgeVariant("Partial_Approved")).toBe("outline");
  });
});
