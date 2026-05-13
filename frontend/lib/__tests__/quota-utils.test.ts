/**
 * Tests for `lib/quota-utils.ts`.
 *
 * These pure helpers drive the quota management dashboard:
 * - `calculateTotalQuota` sums across (sub-type × college) cells in a
 *   matrix-mode scholarship.
 * - `calculateUsagePercentage` powers the progress bars (and the
 *   division-by-zero guard prevents NaN from leaking into the UI).
 * - `getQuotaStatusColor` turns percent into a traffic-light color the
 *   admin uses to triage which slots are about to be exhausted.
 *
 * Wrong rendering = admins miss a near-quota condition and over-approve.
 *
 * 13 cases.
 */
import type { MatrixQuotaData, QuotaCell, QuotaSummary } from "@/types/quota";
import {
  calculateTotalQuota,
  calculateUsagePercentage,
  getQuotaStatusColor,
} from "../quota-utils";

const cell = (total: number): QuotaCell => ({
  total_quota: total,
  used: 0,
  available: total,
  applications: 0,
});

const emptySummary: QuotaSummary = {
  total_quota: 0,
  total_used: 0,
  total_available: 0,
};

const buildData = (
  phd_quotas: MatrixQuotaData["phd_quotas"],
): MatrixQuotaData => ({
  academic_year: "114",
  period_type: "academic_year",
  phd_quotas,
  grand_total: emptySummary,
});

// ─── calculateTotalQuota ─────────────────────────────────────────────

describe("calculateTotalQuota", () => {
  it("sums total_quota across all sub-type × college cells", () => {
    const data = buildData({
      nstc: { E: cell(5), C: cell(3) },
      moe_1w: { E: cell(2), M: cell(7) },
    });
    expect(calculateTotalQuota(data)).toBe(17);
  });

  it("returns 0 for empty phd_quotas", () => {
    expect(calculateTotalQuota(buildData({}))).toBe(0);
  });

  it("ignores other fields on a QuotaCell (only total_quota is summed)", () => {
    /** Important: a cell's `used` doesn't shift the total — the function is
     * computing capacity, not remaining. Pin so a future refactor doesn't
     * accidentally subtract `used`. */
    const data = buildData({
      nstc: {
        E: { total_quota: 10, used: 9, available: 1, applications: 9 },
      },
    });
    expect(calculateTotalQuota(data)).toBe(10);
  });
});

// ─── calculateUsagePercentage ────────────────────────────────────────

describe("calculateUsagePercentage", () => {
  it("returns 0 when total is 0 (divide-by-zero guard)", () => {
    /** No quota configured ⇒ 0% (prevents NaN from leaking into a JSX
     * progress-bar 'width: NaN%' which would crash CSS). */
    expect(calculateUsagePercentage(0, 0)).toBe(0);
    expect(calculateUsagePercentage(5, 0)).toBe(0);
  });

  it("rounds to nearest integer", () => {
    /** Math.round(): 0.5 → 1, 0.4 → 0, etc. Pin so future refactors don't
     * silently switch to floor/ceil (would change ranking display). */
    expect(calculateUsagePercentage(1, 3)).toBe(33); // 33.333...
    expect(calculateUsagePercentage(2, 3)).toBe(67); // 66.666...
    expect(calculateUsagePercentage(1, 2)).toBe(50);
  });

  it("returns 100 at exact full usage", () => {
    expect(calculateUsagePercentage(10, 10)).toBe(100);
  });

  it("over-100% if used > total (e.g., manual oversubscription)", () => {
    /** No clamping — admins manually adjusting allocations can see >100%.
     * The UI uses this to flag oversubscription explicitly. */
    expect(calculateUsagePercentage(15, 10)).toBe(150);
  });
});

// ─── getQuotaStatusColor ─────────────────────────────────────────────

describe("getQuotaStatusColor", () => {
  it("returns red when ≥ 95%", () => {
    /** The critical-near-quota threshold. Admins use red as the
     * 'don't approve more without checking' signal. */
    expect(getQuotaStatusColor(95)).toBe("red");
    expect(getQuotaStatusColor(100)).toBe("red");
    expect(getQuotaStatusColor(150)).toBe("red");
  });

  it("returns orange in the 80-94 range", () => {
    /** Warning band — admin should plan but not panic. */
    expect(getQuotaStatusColor(80)).toBe("orange");
    expect(getQuotaStatusColor(94)).toBe("orange");
  });

  it("returns yellow in the 50-79 range", () => {
    /** Mid-usage — informational. */
    expect(getQuotaStatusColor(50)).toBe("yellow");
    expect(getQuotaStatusColor(79)).toBe("yellow");
  });

  it("returns green below 50%", () => {
    /** Healthy capacity. */
    expect(getQuotaStatusColor(0)).toBe("green");
    expect(getQuotaStatusColor(49)).toBe("green");
  });

  it("boundary values use ≥ comparison (inclusive)", () => {
    /** Pin the inclusivity at each threshold — admins reporting 'when
     * does it turn red' need exact boundaries. */
    expect(getQuotaStatusColor(94.9)).toBe("orange");
    expect(getQuotaStatusColor(95.0)).toBe("red");
    expect(getQuotaStatusColor(79.9)).toBe("yellow");
    expect(getQuotaStatusColor(80.0)).toBe("orange");
  });
});
