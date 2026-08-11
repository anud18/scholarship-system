/**
 * buildCollegeQuotaGrid — the live 各學院剩餘名額 grid shared by the matrix and
 * the panel's save gate. Per-college quota is a hard cap, so `overflows` is what
 * blocks 儲存/確認分發; these tests pin the delta math that produces it.
 */

import { buildCollegeQuotaGrid } from "../modules/college-quota-grid";
import type {
  DistributionStudent,
  LocalAlloc,
  QuotaStatus,
  SubTypeConfigCol,
} from "../modules/manual-distribution";
import { makeColKey } from "../modules/manual-distribution";

const COL: SubTypeConfigCol = {
  sub_type: "nstc",
  config_id: 7,
  config_code: "phd_115",
  academic_year: 115,
  is_own: true,
  display_name: "國科會",
  total: 3,
  remaining: 3,
  key: makeColKey("nstc", 7),
};

function quotaStatus(
  byCollege: Record<string, { total: number; allocated: number }> | null
): QuotaStatus {
  return {
    nstc: {
      display_name: "國科會",
      by_config: [
        {
          config_id: 7,
          config_code: "phd_115",
          academic_year: 115,
          is_own: true,
          total: 3,
          remaining: 3,
          by_college:
            byCollege &&
            Object.fromEntries(
              Object.entries(byCollege).map(([code, cell]) => [
                code,
                { ...cell, remaining: cell.total - cell.allocated },
              ])
            ),
        },
      ],
    },
  };
}

function student(over: Partial<DistributionStudent>): DistributionStudent {
  return {
    ranking_item_id: 1,
    application_id: 1,
    rank_position: 1,
    applied_sub_types: ["nstc"],
    rejected_sub_types: [],
    professor_review_items: [],
    college_review_items: [],
    requires_professor_recommendation: false,
    allocated_sub_type: null,
    allocation_config_id: null,
    is_allocated: false,
    status: "ranked",
    quota_allocation_status: null,
    holds_award: false,
    revoke_reason: null,
    suspend_reason: null,
    college_rejected: false,
    college_code: "A",
    college_name: "工學院",
    department_name: "資工系",
    term_count: null,
    student_name: "S",
    nationality: "TW",
    enrollment_date: "2025-09-01",
    student_id: "111550001",
    application_identity: "phd",
    is_renewal: false,
    renewal_year: null,
    renewal_sub_type: null,
    received_months: null,
    received_months_source: null,
    is_supplementary: false,
    ...over,
  };
}

const staged = (entries: Array<[number, LocalAlloc | null]>) =>
  new Map<number, LocalAlloc | null>(entries);

describe("buildCollegeQuotaGrid", () => {
  it("nets unsaved checkboxes out of the college's remaining", () => {
    const grid = buildCollegeQuotaGrid({
      cols: [COL],
      quotaStatus: quotaStatus({ A: { total: 2, allocated: 0 } }),
      students: [student({ ranking_item_id: 1 })],
      localAllocations: staged([[1, { sub_type: "nstc", config_id: 7 }]]),
    });

    expect(grid.cell("A", COL.key)).toEqual({
      total: 2,
      allocated: 0,
      remaining: 1,
    });
    expect(grid.overflows).toEqual([]);
  });

  it("does not double-count an allocation that is already saved", () => {
    const grid = buildCollegeQuotaGrid({
      cols: [COL],
      quotaStatus: quotaStatus({ A: { total: 2, allocated: 1 } }),
      students: [
        student({
          ranking_item_id: 1,
          is_allocated: true,
          allocated_sub_type: "nstc",
          allocation_config_id: 7,
        }),
      ],
      localAllocations: staged([[1, { sub_type: "nstc", config_id: 7 }]]),
    });

    expect(grid.cell("A", COL.key)?.remaining).toBe(1);
  });

  it("reports an overflow when staged checkboxes exceed the college's cell", () => {
    const grid = buildCollegeQuotaGrid({
      cols: [COL],
      quotaStatus: quotaStatus({ A: { total: 1, allocated: 0 } }),
      students: [
        student({ ranking_item_id: 1 }),
        student({ ranking_item_id: 2, application_id: 2 }),
      ],
      localAllocations: staged([
        [1, { sub_type: "nstc", config_id: 7 }],
        [2, { sub_type: "nstc", config_id: 7 }],
      ]),
    });

    expect(grid.cell("A", COL.key)?.remaining).toBe(-1);
    expect(grid.overflows).toEqual([
      { collegeCode: "A", col: COL, total: 1, used: 2 },
    ]);
  });

  it("surfaces a college that only exists as a staged allocation (zero quota)", () => {
    const grid = buildCollegeQuotaGrid({
      cols: [COL],
      quotaStatus: quotaStatus({ A: { total: 1, allocated: 0 } }),
      students: [student({ ranking_item_id: 1, college_code: "ZZ" })],
      localAllocations: staged([[1, { sub_type: "nstc", config_id: 7 }]]),
    });

    expect(grid.collegeCodes).toEqual(["A", "ZZ"]);
    expect(grid.overflows).toEqual([
      { collegeCode: "ZZ", col: COL, total: 0, used: 1 },
    ]);
  });

  it("reads a college with NO cell in a matrix column as 0 quota, not unconstrained", () => {
    // The tick-time guard asks for the cell BEFORE staging anything, so a
    // missing entry must already read as full — otherwise the first tick into a
    // zero-quota college is accepted and only the second one is refused.
    const grid = buildCollegeQuotaGrid({
      cols: [COL],
      quotaStatus: quotaStatus({ A: { total: 1, allocated: 0 } }),
      students: [student({ ranking_item_id: 1, college_code: "ZZ" })],
      localAllocations: staged([[1, null]]),
    });

    expect(grid.hasCollegeSplit(COL.key)).toBe(true);
    expect(grid.cell("ZZ", COL.key)).toEqual({
      total: 0,
      allocated: 0,
      remaining: 0,
    });
    expect(grid.overflows).toEqual([]);
  });

  it("ignores renewal rows — their consumption is counted server-side", () => {
    const grid = buildCollegeQuotaGrid({
      cols: [COL],
      quotaStatus: quotaStatus({ A: { total: 1, allocated: 1 } }),
      students: [student({ ranking_item_id: 1, is_renewal: true })],
      localAllocations: staged([[1, { sub_type: "nstc", config_id: 7 }]]),
    });

    expect(grid.cell("A", COL.key)?.remaining).toBe(0);
    expect(grid.overflows).toEqual([]);
  });

  it("has no cell for a non-matrix column", () => {
    const grid = buildCollegeQuotaGrid({
      cols: [COL],
      quotaStatus: quotaStatus(null),
      students: [student({ ranking_item_id: 1 })],
      localAllocations: staged([[1, { sub_type: "nstc", config_id: 7 }]]),
    });

    expect(grid.collegeCodes).toEqual([]);
    expect(grid.hasCollegeSplit(COL.key)).toBe(false);
    expect(grid.cell("A", COL.key)).toBeNull();
    expect(grid.overflows).toEqual([]);
  });
});
