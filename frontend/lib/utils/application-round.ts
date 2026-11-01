/**
 * 多梯次申請 helpers shared by the admin round editor, the college ranking
 * table, the manual-distribution grid and the student portal.
 *
 * Round 1 is a configuration's own application window (every sub-type);
 * rounds 2.. come from the configuration's application_rounds. A college
 * ranking keeps 續領 → 第一梯次 → 第二梯次 … (mirrors backend ranking_groups.py).
 */

export const FIRST_APPLICATION_ROUND = 1;

const CHINESE_NUMERALS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];

/** 第一梯次 / 第二梯次 / …（超過十用阿拉伯數字） */
export function roundLabel(roundNumber: number, locale: "zh" | "en" = "zh"): string {
  if (locale === "en") return `Round ${roundNumber}`;
  if (roundNumber > 0 && roundNumber < CHINESE_NUMERALS.length) {
    return `第${CHINESE_NUMERALS[roundNumber]}梯次`;
  }
  return `第${roundNumber}梯次`;
}

/** An application's 梯次 (missing / null → round 1). */
export function applicationRoundOf(item: { application_round?: number | null }): number {
  return item.application_round || FIRST_APPLICATION_ROUND;
}

/** 批次匯入 / 補充匯入 workbook: what the 申請梯次 column takes. */
export const IMPORT_ROUND_COLUMN_HINT = {
  zh: "「申請梯次」欄填梯次編號（1 = 第一梯次、2 = 第二梯次…）；只有第一梯次時可留白，設有多個梯次時必填。",
  en: "The 申請梯次 column takes the round number (1, 2, …); it may stay blank only while the scholarship has a single round.",
} as const;

/** 梯次 label shown to admins and colleges: 續領 for a renewal, else 第N梯次 (第一梯次 included). */
export function applicationRoundLabel(
  item: { is_renewal?: boolean | null; application_round?: number | null },
  locale: "zh" | "en" = "zh"
): string {
  if (item.is_renewal) return locale === "en" ? "Renewal" : "續領";
  return roundLabel(applicationRoundOf(item), locale);
}

interface RankedRow {
  is_renewal?: boolean;
  application_round?: number | null;
  college_rejected?: boolean;
}

/** Sort group in a college ranking: 0 = 續領, then the round number. */
export function rankingGroup(row: RankedRow): number {
  return row.is_renewal ? 0 : applicationRoundOf(row);
}

/**
 * Pairs of non-rejected rows in the wrong group order (a later group ranked above
 * an earlier one). 0 means the order is valid; a drag may only lower it.
 */
export function countGroupOrderInversions(rows: RankedRow[]): number {
  const groups = rows.filter(row => !row.college_rejected).map(rankingGroup);
  let inversions = 0;
  groups.forEach((group, i) => {
    for (let j = i + 1; j < groups.length; j += 1) {
      if (groups[j] < group) inversions += 1;
    }
  });
  return inversions;
}

/**
 * The first group-order violation of rows in rank order, or null when valid.
 * College-rejected rows ('N', parked at the end) are exempt.
 */
export function findGroupOrderViolation(rows: RankedRow[]): string | null {
  let highest: number | null = null;
  for (const row of rows) {
    if (row.college_rejected) continue;
    const group = rankingGroup(row);
    if (highest !== null && group < highest) {
      if (group === 0) return "續領學生的排名必須在所有新申請學生之前";
      return `${roundLabel(highest)}申請學生的排名必須在${roundLabel(group)}之後`;
    }
    highest = highest === null ? group : Math.max(highest, group);
  }
  return null;
}
