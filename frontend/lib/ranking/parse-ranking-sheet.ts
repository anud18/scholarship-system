/**
 * Pure parser for the 學生資料彙整表 ranking-import format.
 *
 * Input rows are the objects produced by `XLSX.utils.sheet_to_json(ws, { range: 1 })`
 * — keyed by the export's row-2 headers (the merged title on row 1 is skipped by
 * the caller via `range: 1`). We only read the three columns the backend
 * `POST /import-excel` needs; every other 彙整表 column is ignored.
 *
 * Data rows start at Excel row 3 (row 1 = title, row 2 = headers), so the
 * human-facing row number for error messages is `index + 3`.
 */

// Header strings — must match backend STATIC_HEADERS exactly
// (college_ranking_export_service.py STATIC_HEADERS indices 12 / 7 / 1).
const COL_STUDENT_ID = "學號";
const COL_STUDENT_NAME = "學生中文姓名";
const COL_RANK = "學院初審會議之學院排序";

const FIRST_DATA_EXCEL_ROW = 3;

export interface ExcelRankingImportRow {
  student_id: string;
  student_name: string;
  rank_position: number | "N"; // integer rank, or "N" for rejected
}

export interface ParseResult {
  importData: ExcelRankingImportRow[];
  errors: string[];
}

// Count how many times each value appears, in first-seen order.
function countOccurrences<T>(values: T[]): Map<T, number> {
  const counts = new Map<T, number>();
  values.forEach(v => counts.set(v, (counts.get(v) ?? 0) + 1));
  return counts;
}

export function parseRankingSheet(
  rows: Array<Record<string, unknown>>
): ParseResult {
  const errors: string[] = [];
  const importData: ExcelRankingImportRow[] = [];

  rows.forEach((row, index) => {
    const rowNum = index + FIRST_DATA_EXCEL_ROW;
    const studentId = String(row[COL_STUDENT_ID] ?? "").trim();
    const studentName = String(row[COL_STUDENT_NAME] ?? "").trim();
    const rawRank = row[COL_RANK];

    if (!studentId) return; // skip empty rows

    if (
      rawRank === undefined ||
      rawRank === null ||
      String(rawRank).trim() === ""
    ) {
      errors.push(`第 ${rowNum} 行排名欄位為空（學號：${studentId}）`);
      return;
    }

    const rankStr = String(rawRank).trim();

    if (rankStr.toUpperCase() === "N") {
      importData.push({
        student_id: studentId,
        student_name: studentName,
        rank_position: "N",
      });
      return;
    }

    const rankNum = Number(rankStr);
    if (!Number.isInteger(rankNum) || rankNum < 1) {
      errors.push(
        `第 ${rowNum} 行排名格式無效：'${rankStr}'（學號：${studentId}）`
      );
      return;
    }
    importData.push({
      student_id: studentId,
      student_name: studentName,
      rank_position: rankNum,
    });
  });

  // Duplicate 學號
  const duplicateStudentIds = [
    ...countOccurrences(importData.map(item => item.student_id)),
  ]
    .filter(([, count]) => count > 1)
    .map(([studentId]) => studentId);
  if (duplicateStudentIds.length > 0) {
    errors.push(`學號重複：${duplicateStudentIds.join(", ")}`);
  }

  // Duplicate integer ranks
  const integerRanks = importData
    .filter(item => typeof item.rank_position === "number")
    .map(item => item.rank_position as number);

  countOccurrences(integerRanks).forEach((count, rank) => {
    if (count > 1) {
      errors.push(`排名 ${rank} 重複出現（${count} 次）`);
    }
  });

  // Consecutive from 1 (only when no prior errors, mirroring legacy behavior)
  if (integerRanks.length > 0 && errors.length === 0) {
    const rankSet = new Set(integerRanks);
    const missing: number[] = [];
    for (let i = 1; i <= integerRanks.length; i++) {
      if (!rankSet.has(i)) missing.push(i);
    }
    if (missing.length > 0) {
      errors.push(`排名不連續：缺少第 ${missing.join(", ")} 名`);
    }
  }

  return { importData, errors };
}
