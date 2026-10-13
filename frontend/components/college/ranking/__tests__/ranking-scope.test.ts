/**
 * Tests for `components/college/ranking/ranking-scope.ts` — the scope rules
 * behind multiple draft rankings and the lock collapse (確認排名 deletes the
 * college's other rankings in the same scope).
 */

import {
  buildDefaultRankingName,
  findBlockingRanking,
  findScopeSiblings,
  isUndeletableRanking,
  pickDefaultRankingId,
  resolveRankingTarget,
  type RankingScopeFields,
} from "../ranking-scope";

function ranking(overrides: Partial<RankingScopeFields> & { id: number }): RankingScopeFields {
  return {
    ranking_name: `排名 ${overrides.id}`,
    scholarship_type_id: 1,
    sub_type_code: "default",
    academic_year: 114,
    semester: null,
    college_code: "C",
    is_finalized: false,
    distribution_executed: false,
    ...overrides,
  };
}

describe("findScopeSiblings", () => {
  it("returns the other rankings of the same scope, never the target itself", () => {
    const target = ranking({ id: 1 });
    const rankings = [target, ranking({ id: 2 }), ranking({ id: 3 })];
    expect(findScopeSiblings(rankings, target).map(r => r.id)).toEqual([2, 3]);
  });

  it("leaves other colleges, sub-types, years, semesters and scholarships alone", () => {
    // Pin #1034: locking one college's ranking must never touch another's.
    const target = ranking({ id: 1 });
    const rankings = [
      target,
      ranking({ id: 2, college_code: "E" }),
      ranking({ id: 3, sub_type_code: "nstc" }),
      ranking({ id: 4, academic_year: 113 }),
      ranking({ id: 5, semester: "first" }),
      ranking({ id: 6, scholarship_type_id: 2 }),
      ranking({ id: 7, college_code: null }),
    ];
    expect(findScopeSiblings(rankings, target)).toEqual([]);
  });

  it("treats NULL and 'yearly' semesters as one period (backend COALESCE)", () => {
    const target = ranking({ id: 1, semester: null });
    const rankings = [target, ranking({ id: 2, semester: "yearly" }), ranking({ id: 3, semester: "YEARLY" })];
    expect(findScopeSiblings(rankings, target).map(r => r.id)).toEqual([2, 3]);
  });

  it("matches admin global rankings (college_code NULL) only with each other", () => {
    const target = ranking({ id: 1, college_code: null });
    const rankings = [target, ranking({ id: 2, college_code: undefined }), ranking({ id: 3 })];
    expect(findScopeSiblings(rankings, target).map(r => r.id)).toEqual([2]);
  });
});

describe("findBlockingRanking", () => {
  // The scope 建立新排名 would create into (the ranking() defaults).
  const target = {
    scholarship_type_id: 1,
    sub_type_code: "default",
    academic_year: 114,
    semester: null,
    college_code: "C",
  };

  it("returns nothing while the scope holds only drafts", () => {
    const rankings = [ranking({ id: 1 }), ranking({ id: 2 })];
    expect(findBlockingRanking(rankings, target)).toBeUndefined();
  });

  it("returns the finalized ranking of the scope", () => {
    const rankings = [ranking({ id: 1 }), ranking({ id: 2, is_finalized: true })];
    expect(findBlockingRanking(rankings, target)?.id).toBe(2);
  });

  it("also blocks on a distributed ranking that was unlocked", () => {
    // The backend refuses to create beside a distributed ranking even while
    // it is unlocked (補充匯入 window); new applications go in via sync.
    const rankings = [ranking({ id: 1 }), ranking({ id: 2, distribution_executed: true })];
    expect(findBlockingRanking(rankings, target)?.id).toBe(2);
  });

  it("blocks on allocation results before distribution_executed is set", () => {
    // The backend's "settled" also covers items with allocation state (e.g.
    // an allocate() saved, then the ranking unlocked); the list reports it.
    const rankings = [ranking({ id: 1 }), ranking({ id: 2, is_settled: true })];
    expect(findBlockingRanking(rankings, target)?.id).toBe(2);
  });

  it("does not block on a ranking only a roster references", () => {
    // Matches the backend: create checks finalized/settled, not rosters.
    const rankings = [ranking({ id: 1, is_roster_referenced: true })];
    expect(findBlockingRanking(rankings, target)).toBeUndefined();
  });

  it("prefers the finalized ranking over a distributed one", () => {
    const rankings = [
      ranking({ id: 1, distribution_executed: true }),
      ranking({ id: 2, is_finalized: true }),
    ];
    expect(findBlockingRanking(rankings, target)?.id).toBe(2);
  });

  it("ignores locks in any other scope, including other periods and scholarships", () => {
    // The list may span every period (an unset period filter) — last year's
    // locked or distributed ranking must not disable this year's create.
    const rankings = [
      ranking({ id: 1, sub_type_code: "nstc", is_finalized: true }),
      ranking({ id: 2, college_code: "E", is_finalized: true }),
      ranking({ id: 3, academic_year: 113, is_finalized: true, distribution_executed: true }),
      ranking({ id: 4, semester: "first", is_finalized: true }),
      ranking({ id: 5, scholarship_type_id: 2, is_finalized: true }),
    ];
    expect(findBlockingRanking(rankings, target)).toBeUndefined();
  });

  it("treats NULL and 'yearly' semesters as one period", () => {
    const rankings = [ranking({ id: 1, semester: "yearly", is_finalized: true })];
    expect(findBlockingRanking(rankings, target)?.id).toBe(1);
  });

  it("treats a missing college code as the admin global scope", () => {
    const rankings = [ranking({ id: 1, college_code: null, is_finalized: true })];
    expect(findBlockingRanking(rankings, { ...target, college_code: undefined })?.id).toBe(1);
    expect(findBlockingRanking(rankings, target)).toBeUndefined();
  });
});

describe("isUndeletableRanking", () => {
  it("accepts a plain draft", () => {
    expect(isUndeletableRanking(ranking({ id: 1 }))).toBe(false);
  });

  it.each([
    ["locked", { is_finalized: true }],
    ["distributed", { distribution_executed: true }],
    ["holding allocation results", { is_settled: true }],
    ["used by a roster", { is_roster_referenced: true }],
  ])("refuses a ranking that is %s (the backend answers 409)", (_label, overrides) => {
    expect(isUndeletableRanking(ranking({ id: 1, ...overrides }))).toBe(true);
  });
});

describe("pickDefaultRankingId", () => {
  it("returns null for an empty list", () => {
    expect(pickDefaultRankingId([])).toBeNull();
  });

  it("prefers the finalized ranking even when newer drafts exist", () => {
    const rankings = [ranking({ id: 9 }), ranking({ id: 4, is_finalized: true }), ranking({ id: 7 })];
    expect(pickDefaultRankingId(rankings)).toBe(4);
  });

  it("falls back to the newest (highest id) draft, whatever the list order", () => {
    const rankings = [ranking({ id: 3 }), ranking({ id: 8 }), ranking({ id: 5 })];
    expect(pickDefaultRankingId(rankings)).toBe(8);
  });
});

describe("buildDefaultRankingName", () => {
  const now = new Date(2026, 9, 3, 9, 5); // 10/03 09:05 local time

  it("appends a zero-padded MM/DD HH:mm stamp so drafts are distinguishable", () => {
    expect(
      buildDefaultRankingName({
        scholarshipName: "博士生獎學金",
        academicYear: 114,
        semesterLabel: "上學期",
        now,
      })
    ).toBe("博士生獎學金 - 114 上學期 (10/03 09:05)");
  });

  it("adds a numeric suffix when the name is already taken", () => {
    const base = "博士生獎學金 - 114 全年 (10/03 09:05)";
    expect(
      buildDefaultRankingName({
        scholarshipName: "博士生獎學金",
        academicYear: 114,
        semesterLabel: "全年",
        now,
        existingNames: [base, `${base} (2)`],
      })
    ).toBe(`${base} (3)`);
  });
});

describe("resolveRankingTarget", () => {
  const configs = [
    { id: 11, name: "獎學金甲", subTypes: [{ code: "default" }] },
    { id: 22, name: "獎學金乙", subTypes: [{ code: "nstc" }] },
  ];
  const types = [
    { code: "a", name: "獎學金甲" },
    { code: "b", name: "獎學金乙" },
  ];

  it("uses the config matching the active scholarship tab", () => {
    expect(resolveRankingTarget(types, configs, "b")).toEqual({
      scholarshipTypeId: 22,
      subTypeCode: "nstc",
    });
  });

  it("falls back to the first config when the tab matches none", () => {
    expect(resolveRankingTarget(types, configs, "zzz")).toEqual({
      scholarshipTypeId: 11,
      subTypeCode: "default",
    });
  });

  it("returns an empty target before the configs are loaded", () => {
    expect(resolveRankingTarget(undefined, [], "a")).toEqual({
      scholarshipTypeId: undefined,
      subTypeCode: undefined,
    });
  });
});
