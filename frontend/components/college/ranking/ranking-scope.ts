/**
 * Pure helpers for the college ranking scope rules.
 *
 * A ranking's scope is (scholarship type, sub-type, academic year, semester,
 * college). A college may keep several DRAFT rankings per scope; 確認排名 locks
 * one of them and the backend deletes the others, so a scope never holds more
 * than one finalized ranking. While a finalized (or settled) ranking exists
 * in the scope the backend refuses to create another (409) — the panel uses
 * these helpers to say so before the user clicks.
 */

/** The ranking-list fields the scope rules read (GET /college-review/rankings). */
export interface RankingScopeFields {
  id: number;
  ranking_name?: string;
  scholarship_type_id?: number;
  sub_type_code?: string | null;
  academic_year?: number;
  semester?: string | null;
  college_code?: string | null;
  is_finalized?: boolean | null;
  distribution_executed?: boolean | null;
  /**
   * Distributed, or holding allocation results before distribution_executed
   * is set (backend `_load_settled_ids`).
   */
  is_settled?: boolean | null;
  /** Used by a 造冊 roster. */
  is_roster_referenced?: boolean | null;
}

/** Distribution state that blocks creating another ranking in the scope. */
function isSettled(ranking: RankingScopeFields): boolean {
  return ranking.is_settled === true || ranking.distribution_executed === true;
}

/**
 * The backend never deletes this ranking: not by 刪除, and not by another
 * ranking's lock (that lock answers 409 and deletes nothing).
 */
export function isUndeletableRanking(ranking: RankingScopeFields): boolean {
  return (
    ranking.is_finalized === true ||
    isSettled(ranking) ||
    ranking.is_roster_referenced === true
  );
}

/** The five fields that make up a ranking's scope. */
export type RankingScope = Pick<
  RankingScopeFields,
  "scholarship_type_id" | "sub_type_code" | "academic_year" | "semester" | "college_code"
>;

// Yearly scholarships store the semester as NULL or "yearly"; both are one
// period, matching the backend's COALESCE(semester, 'yearly').
function semesterKey(semester: string | null | undefined): string {
  const value = semester ? semester.toLowerCase() : "";
  return value === "" || value === "yearly" ? "yearly" : value;
}

// NULL college_code is an admin's global ranking; "" never names a college.
function collegeKey(collegeCode: string | null | undefined): string {
  return collegeCode || "";
}

function subTypeKey(subTypeCode: string | null | undefined): string {
  return subTypeCode || "";
}

function isSameScope(a: RankingScope, b: RankingScope): boolean {
  return (
    a.scholarship_type_id === b.scholarship_type_id &&
    a.academic_year === b.academic_year &&
    semesterKey(a.semester) === semesterKey(b.semester) &&
    subTypeKey(a.sub_type_code) === subTypeKey(b.sub_type_code) &&
    collegeKey(a.college_code) === collegeKey(b.college_code)
  );
}

/**
 * The other rankings in `target`'s scope — exactly the ones finalizing
 * `target` deletes. Compares the full scope, so `rankings` may span periods.
 */
export function findScopeSiblings<T extends RankingScopeFields>(
  rankings: readonly T[],
  target: RankingScopeFields
): T[] {
  return rankings.filter(
    ranking => ranking.id !== target.id && isSameScope(ranking, target)
  );
}

/**
 * The ranking that blocks creating another one in `target`'s scope: a
 * finalized ranking first, else a settled one. Compares the full scope, so
 * `rankings` may span scholarships and periods.
 */
export function findBlockingRanking<T extends RankingScopeFields>(
  rankings: readonly T[],
  target: RankingScope
): T | undefined {
  const inScope = rankings.filter(ranking => isSameScope(ranking, target));
  return (
    inScope.find(ranking => ranking.is_finalized === true) ??
    inScope.find(isSettled)
  );
}

/**
 * The ranking to open when the selection is empty or gone: the finalized one
 * (after a lock it is the only one left in its scope), else the newest draft.
 */
export function pickDefaultRankingId(
  rankings: readonly RankingScopeFields[]
): number | null {
  if (rankings.length === 0) return null;
  const newestFirst = [...rankings].sort((a, b) => b.id - a.id);
  const finalized = newestFirst.find(ranking => ranking.is_finalized === true);
  return (finalized ?? newestFirst[0]).id;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

/**
 * Default name for a new draft, e.g. 「博士生獎學金 - 114 上學期 (10/13 14:05)」.
 * The timestamp tells drafts apart on the cards; a name already in
 * `existingNames` (two drafts in the same minute) gets a " (2)", " (3)" … suffix.
 */
export function buildDefaultRankingName({
  scholarshipName,
  academicYear,
  semesterLabel,
  now = new Date(),
  existingNames = [],
}: {
  scholarshipName: string;
  academicYear: number;
  semesterLabel: string;
  now?: Date;
  existingNames?: readonly string[];
}): string {
  const stamp = `${pad2(now.getMonth() + 1)}/${pad2(now.getDate())} ${pad2(now.getHours())}:${pad2(now.getMinutes())}`;
  const baseName = `${scholarshipName} - ${academicYear} ${semesterLabel} (${stamp})`;
  const taken = new Set(existingNames);
  let name = baseName;
  for (let suffix = 2; taken.has(name); suffix++) {
    name = `${baseName} (${suffix})`;
  }
  return name;
}

/**
 * The scholarship type id and sub-type a new ranking is created for: the
 * config whose name matches the active scholarship tab, falling back to the
 * first config. Shared by 建立新排名 and the check that disables it, so both
 * always look at the same scope.
 */
export function resolveRankingTarget(
  scholarshipTypes: ReadonlyArray<{ code: string; name: string }> | undefined,
  configs: ReadonlyArray<{ id: number; name: string; subTypes: ReadonlyArray<{ code: string }> }>,
  activeScholarshipCode: string | undefined
): { scholarshipTypeId?: number; subTypeCode?: string } {
  const activeType = scholarshipTypes?.find(
    type => type.code === activeScholarshipCode
  );
  const config = configs.find(item => item.name === activeType?.name);
  return {
    scholarshipTypeId: config?.id || configs[0]?.id,
    subTypeCode: config?.subTypes[0]?.code || configs[0]?.subTypes[0]?.code,
  };
}
