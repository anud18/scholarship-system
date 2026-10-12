/**
 * 學院顯示編號 (各學院編號對照表)
 *
 * Display-only numbering admins use to refer to colleges, keyed by the SIS
 * academy code. It does NOT replace the SIS code mapping — codes stay the
 * identity everywhere; the number is only prefixed onto rendered names.
 *
 * Mirrored in backend/app/utils/college_display_number.py — keep in sync.
 */

export const COLLEGE_DISPLAY_NUMBERS: Readonly<Record<string, number>> = {
  A: 1, // 人文藝術與社會學院
  I: 2, // 工學院
  B: 3, // 工程生物科學學院
  K: 4, // 客家文化學院
  S: 5, // 理學院
  C: 6, // 資訊學院
  E: 7, // 電機學院
  M: 8, // 管理學院
  O: 9, // 光電學院
  L: 10, // 科技法律學院
  D: 11, // 國際半導體產業學院
  G: 12, // 智慧科學暨綠能學院
  "2": 13, // 牙醫學院
  "7": 14, // 生命科學院
  "6": 15, // 生物醫學暨工程學院
  "1": 16, // 醫學院
  "5": 17, // 藥物科學院
  "3": 18, // 護理學院
  F: 19, // 產學創新研究學院
};

export function getCollegeDisplayNumber(code: string): number | undefined {
  return COLLEGE_DISPLAY_NUMBERS[code.trim()];
}

/** "6. 資訊學院" for numbered codes; the bare name otherwise. */
export function formatCollegeName(code: string, name: string): string {
  const number = getCollegeDisplayNumber(code);
  return number === undefined ? name : `${number}. ${name}`;
}

/**
 * New array sorted by display number; unnumbered colleges keep their original
 * relative order after the numbered ones.
 */
export function sortByCollegeDisplayNumber<T extends { code: string }>(
  colleges: readonly T[]
): T[] {
  const rank = (c: T) => getCollegeDisplayNumber(c.code) ?? Number.POSITIVE_INFINITY;
  return [...colleges].sort((a, b) => rank(a) - rank(b));
}
