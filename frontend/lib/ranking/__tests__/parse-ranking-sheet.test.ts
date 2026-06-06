import {
  parseRankingSheet,
  type ExcelRankingImportRow,
} from "@/lib/ranking/parse-ranking-sheet";

// Each row mimics XLSX.utils.sheet_to_json(ws, { range: 1 }) output:
// keys are the row-2 headers of the 學生資料彙整表 export.
const rowOf = (id: string, name: string, rank: unknown) => ({
  學號: id,
  學生中文姓名: name,
  學院初審會議之學院排序: rank,
});

describe("parseRankingSheet", () => {
  it("reads 學號 + 學生中文姓名 + 學院初審會議之學院排序 for integer ranks", () => {
    const { importData, errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", 2),
    ]);
    expect(errors).toEqual([]);
    expect(importData).toEqual<ExcelRankingImportRow[]>([
      { student_id: "310460099", student_name: "王小明", rank_position: 1 },
      { student_id: "310460100", student_name: "李小華", rank_position: 2 },
    ]);
  });

  it("treats N (any case) as a rejected marker, not a numeric rank", () => {
    const { importData, errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", "n"),
    ]);
    expect(errors).toEqual([]);
    expect(importData[1].rank_position).toBe("N");
  });

  it("skips rows with an empty 學號", () => {
    const { importData } = parseRankingSheet([
      rowOf("", "", ""),
      rowOf("310460099", "王小明", 1),
    ]);
    expect(importData).toHaveLength(1);
    expect(importData[0].student_id).toBe("310460099");
  });

  it("errors when the rank cell is blank (data row = index + 3)", () => {
    const { errors } = parseRankingSheet([rowOf("310460099", "王小明", "")]);
    expect(errors).toEqual([
      "第 3 行排名欄位為空（學號：310460099）",
    ]);
  });

  it("errors on a non-positive-integer rank", () => {
    const { errors } = parseRankingSheet([rowOf("310460099", "王小明", "0")]);
    expect(errors[0]).toContain("排名格式無效");
  });

  it("errors on duplicate 學號", () => {
    const { errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460099", "王小明", 2),
    ]);
    expect(errors.some(e => e.includes("學號重複"))).toBe(true);
  });

  it("errors on duplicate integer ranks", () => {
    const { errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", 1),
    ]);
    expect(errors.some(e => e.includes("排名 1 重複出現"))).toBe(true);
  });

  it("errors when integer ranks are not consecutive from 1", () => {
    const { errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", 3),
    ]);
    expect(errors.some(e => e.includes("排名不連續"))).toBe(true);
  });

  it("does not treat N as a gap: ranks 1,2 + one N are consecutive", () => {
    const { importData, errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", 2),
      rowOf("310460101", "張小強", "N"),
    ]);
    expect(errors).toEqual([]);
    expect(importData).toHaveLength(3);
    expect(importData[2].rank_position).toBe("N");
  });

  it("surfaces both 學號重複 and 排名不連續 in one pass (a dup 學號 does not hide the gap)", () => {
    const { errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460099", "王小明", 3),
    ]);
    expect(errors.some(e => e.includes("學號重複"))).toBe(true);
    expect(errors.some(e => e.includes("排名不連續"))).toBe(true);
  });

  it("suppresses the consecutive check when a row was dropped by a blank rank", () => {
    const { errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", ""), // dropped → importData incomplete
      rowOf("310460101", "張小強", 3),
    ]);
    expect(errors.some(e => e.includes("排名欄位為空"))).toBe(true);
    // no false "排名不連續：缺少第 2 名" from the incomplete set
    expect(errors.some(e => e.includes("排名不連續"))).toBe(false);
  });
});
