/*
 * 申請人數統計 — pure tally logic (no DOM, no network).
 *
 * Input is the 學生資料彙整表 parsed by RenewalCompare.parseSheet (one record
 * per applicant row, `row` = the raw cells). Output tables follow the office's
 * 「統計各學院各年級申請人數」 template: one row per college in the template's
 * order (all 19, zero rows included), one column per 年級 (or per 國籍 for the
 * 外籍生 report, which also ends with a 國籍分布概況 text column), then 合計.
 *
 * Loaded as a classic <script> (window.ApplicantStats) and via require() in
 * the Node tests.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ApplicantStats = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // The template's 編號 order. 彙整表 cells look like "16. 醫學院" / "1. 人社院":
  // the number prefix is this 編號, so it is the primary key; names and the
  // short forms used in the 彙整表 are a fallback for cells without a prefix.
  const COLLEGES = Object.freeze([
    { name: "人文藝術與社會學院", aliases: ["人社院", "人文社會學院"] },
    { name: "工學院", aliases: [] },
    { name: "工程生物科學學院", aliases: ["工程生物學院"] },
    { name: "客家文化學院", aliases: ["客家學院"] },
    { name: "理學院", aliases: [] },
    { name: "資訊學院", aliases: [] },
    { name: "電機學院", aliases: [] },
    { name: "管理學院", aliases: [] },
    { name: "光電學院", aliases: [] },
    { name: "科技法律學院", aliases: ["科法學院"] },
    { name: "國際半導體產業學院", aliases: ["半導體學院"] },
    { name: "智慧科學暨綠能學院", aliases: ["綠能學院"] },
    { name: "牙醫學院", aliases: [] },
    { name: "生命科學院", aliases: [] },
    { name: "生物醫學暨工程學院", aliases: ["生醫工學院"] },
    { name: "醫學院", aliases: [] },
    { name: "藥物科學院", aliases: [] },
    { name: "護理學院", aliases: [] },
    { name: "產學創新研究學院", aliases: ["產創學院"] },
  ]);

  const MIN_GRADE_COLUMNS = 9;
  const MAX_GRADE = 12;
  const DOMESTIC_NATIONALITIES = Object.freeze(["中華民國", "臺灣", "台灣", "中華民國(臺灣)", "TAIWAN", "ROC", "R.O.C."]);
  const NSTC_PATTERN = /國科會/;
  const NUMBERED_COLLEGE = /^(\d{1,2})\s*[.．、]\s*(.*)$/;

  const COLUMN_PATTERNS = Object.freeze({
    college: /^學院($|\()/, // not 學院初審會議之學院排序
    grade: /^年級/,
    nationality: /^國籍/,
    category: /^申請獎學金類別/,
  });

  const compact = (value) => (value == null ? "" : String(value).replace(/\s+/g, ""));

  const COLLEGE_BY_NAME = new Map(
    COLLEGES.flatMap((college, i) => [college.name, ...college.aliases].map((n) => [n, i])),
  );

  /** → { index, label } with index into COLLEGES, or index -1 for an unknown college. */
  function resolveCollege(value) {
    const text = compact(value);
    if (!text) return { index: -1, label: "（未填學院）" };
    const numbered = NUMBERED_COLLEGE.exec(text);
    if (numbered) {
      const index = Number(numbered[1]) - 1;
      if (index >= 0 && index < COLLEGES.length) return { index, label: COLLEGES[index].name };
    }
    const name = numbered ? numbered[2] : text;
    const index = COLLEGE_BY_NAME.has(name) ? COLLEGE_BY_NAME.get(name) : -1;
    return index === -1 ? { index, label: name } : { index, label: COLLEGES[index].name };
  }

  /** 年級 as an integer 1..MAX_GRADE, or null when blank/invalid. */
  function parseGrade(value) {
    const text = compact(value).replace(/^博/, "").replace(/年級?$/, "");
    if (!/^\d{1,2}$/.test(text)) return null;
    const grade = Number(text);
    return grade >= 1 && grade <= MAX_GRADE ? grade : null;
  }

  function isForeign(nationality) {
    const text = compact(nationality).toUpperCase();
    return text !== "" && !DOMESTIC_NATIONALITIES.includes(text);
  }

  function appliesNstc(category) {
    return NSTC_PATTERN.test(compact(category));
  }

  /** Column indexes in the 彙整表 header row (-1 when absent). */
  function locateColumns(headerRow) {
    return Object.fromEntries(
      Object.entries(COLUMN_PATTERNS).map(([key, pattern]) => [
        key,
        (headerRow || []).findIndex((cell) => pattern.test(compact(cell))),
      ]),
    );
  }

  /** Per-applicant fields the tallies need. */
  function toApplicants(records, columns) {
    const cell = (row, col) => (col === -1 ? null : row[col]);
    return records.map((record) => ({
      rowNumber: record.rowIndex + 1,
      college: resolveCollege(cell(record.row, columns.college)),
      grade: parseGrade(cell(record.row, columns.grade)),
      nationality: compact(cell(record.row, columns.nationality)),
      foreign: isForeign(cell(record.row, columns.nationality)),
      nationalityBlank: compact(cell(record.row, columns.nationality)) === "",
      nstc: appliesNstc(cell(record.row, columns.category)),
    }));
  }

  const range = (n) => Array.from({ length: n }, (_, i) => i + 1);

  /**
   * College × column counts. `columns` = [{ key, label }], keyOf(applicant)
   * picks the column key. Every template college gets a row (zeros included);
   * unknown colleges are appended after them so nobody silently drops out.
   */
  function tallyByCollege(applicants, columns, keyOf) {
    const unknownLabels = [...new Set(applicants.filter((a) => a.college.index === -1).map((a) => a.college.label))];
    const labels = [...COLLEGES.map((c) => c.name), ...unknownLabels];
    const rows = labels.map((label, i) => {
      const members = applicants.filter((a) => a.college.label === label);
      const counts = columns.map((column) => members.filter((a) => keyOf(a) === column.key).length);
      return { no: i < COLLEGES.length ? i + 1 : null, label, counts, total: members.length };
    });
    const totals = {
      counts: columns.map((_, ci) => rows.reduce((sum, row) => sum + row.counts[ci], 0)),
      total: rows.reduce((sum, row) => sum + row.total, 0),
    };
    return { columns, rows, totals };
  }

  /** 年級 1..max(9, highest), plus 年級未填 only when some 年級 is blank. */
  function gradeColumns(applicants) {
    const maxGrade = applicants.reduce((max, a) => Math.max(max, a.grade || 0), 0);
    const grades = range(Math.max(MIN_GRADE_COLUMNS, maxGrade)).map((g) => ({ key: g, label: g }));
    const unknown = applicants.some((a) => a.grade === null) ? [{ key: null, label: "年級未填" }] : [];
    return [...grades, ...unknown];
  }

  /** One column per 國籍, most applicants first (ties by name). */
  function nationalityColumns(applicants) {
    const counts = applicants.reduce((map, a) => new Map(map).set(a.nationality, (map.get(a.nationality) || 0) + 1), new Map());
    return [...counts.entries()]
      .sort(([nameA, countA], [nameB, countB]) => countB - countA || nameA.localeCompare(nameB, "zh-Hant"))
      .map(([name]) => ({ key: name, label: name }));
  }

  /** "越南2人，印尼1人" — non-zero columns, most first, in column order on ties. */
  function distributionText(columns, counts) {
    return columns
      .map((column, i) => ({ label: column.label, count: counts[i], order: i }))
      .filter((entry) => entry.count > 0)
      .sort((a, b) => b.count - a.count || a.order - b.order)
      .map((entry) => `${entry.label}${entry.count}人`)
      .join("，");
  }

  function tallyByCollegeGrade(applicants) {
    return { ...tallyByCollege(applicants, gradeColumns(applicants), (a) => a.grade), totalLabel: "所有年級合計" };
  }

  function tallyByCollegeNationality(applicants) {
    const table = tallyByCollege(applicants, nationalityColumns(applicants), (a) => a.nationality);
    const withText = (row) => ({ ...row, distribution: distributionText(table.columns, row.counts) });
    return {
      ...table,
      rows: table.rows.map(withText),
      totals: withText(table.totals),
      totalLabel: "外籍生合計",
      distributionLabel: "外籍學生國籍分布概況",
    };
  }

  /** Data-quality notes worth showing next to the tables. */
  function collectWarnings(applicants, columns) {
    const missingColumns = Object.entries({ college: "學院", grade: "年級", nationality: "國籍", category: "申請獎學金類別" })
      .filter(([key]) => columns[key] === -1)
      .map(([, label]) => `找不到「${label}」欄`);
    const rowsWhere = (predicate) => applicants.filter(predicate).map((a) => a.rowNumber);
    const notes = [
      ["學院無法對應到 19 個學院", rowsWhere((a) => a.college.index === -1)],
      ["年級空白或無法辨識", rowsWhere((a) => a.grade === null)],
      ["國籍空白（不計入外籍生）", rowsWhere((a) => a.nationalityBlank)],
    ]
      .filter(([, rows]) => rows.length > 0)
      .map(([label, rows]) => `${label}：第 ${rows.join("、")} 列`);
    return [...missingColumns, ...notes];
  }

  /** Both reports for one 彙整表. */
  function buildReports(records, headerRow) {
    const columns = locateColumns(headerRow);
    const applicants = toApplicants(records, columns);
    return {
      byGrade: tallyByCollegeGrade(applicants),
      foreignNstc: tallyByCollegeNationality(applicants.filter((a) => a.foreign && a.nstc)),
      warnings: collectWarnings(applicants, columns),
      applicantCount: applicants.length,
    };
  }

  /** "115學年度博士生獎學金學生資料彙整表 - 全校" → "115學年度博士生獎學金". */
  function reportPrefix(titleCell, fileName) {
    const fromTitle = compact(titleCell).split("學生資料彙整表")[0];
    if (fromTitle && fromTitle !== compact(titleCell)) return fromTitle;
    return compact(fileName).replace(/\.[^.]+$/, "").split("學生資料彙整表")[0];
  }

  return {
    COLLEGES,
    resolveCollege,
    parseGrade,
    isForeign,
    appliesNstc,
    locateColumns,
    tallyByCollegeGrade,
    tallyByCollegeNationality,
    distributionText,
    buildReports,
    reportPrefix,
  };
});
