/*
 * 續領名單比對 — pure comparison logic (no DOM, no network).
 *
 * Input sheets are arrays of rows (SheetJS `sheet_to_json(ws, {header: 1})`).
 * The 獎勵名冊 workbooks are hand-made: the header row moves (row 2–5),
 * headers span merged cells, and 學號 is stored as a number, so leading zeros
 * of old 7-digit IDs are lost (0856001 → 856001). Matching therefore uses a
 * normalized 學號, and a same-name/different-學號 hit is surfaced for manual
 * review instead of being silently counted as a match.
 *
 * Loaded as a classic <script> in the browser (exposes window.RenewalCompare)
 * and via require() in the Node tests.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.RenewalCompare = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const HEADER_SCAN_ROWS = 12;
  const STUDENT_ID_PATTERN = /^[A-Z]?\d{5,10}$/;
  const ID_HEADER_PATTERN = /^學號/;
  const NAME_HEADER_PATTERN = /^(學生)?(中文)?姓名$/;
  const REMARK_HEADER_PATTERN = /^備註/;

  const STATUS = Object.freeze({
    MATCHED: "matched",
    NAME_ONLY: "name_only",
    NONE: "none",
  });

  const STATUS_LABELS = Object.freeze({
    [STATUS.MATCHED]: "在續領名單",
    [STATUS.NAME_ONLY]: "姓名相同、學號不同（需人工確認）",
    [STATUS.NONE]: "不在續領名單",
  });

  function compactText(value) {
    return value == null ? "" : String(value).replace(/\s+/g, "");
  }

  /** Normalize a 學號 for comparison; returns "" when it is not a 學號. */
  function normalizeStudentId(value) {
    const text = compactText(value).toUpperCase().replace(/\.0+$/, "");
    if (!STUDENT_ID_PATTERN.test(text)) return "";
    const letter = /^[A-Z]/.test(text) ? text[0] : "";
    const digits = (letter ? text.slice(1) : text).replace(/^0+/, "");
    return letter + digits;
  }

  function normalizeName(value) {
    return compactText(value);
  }

  function findColumn(row, pattern) {
    return (row || []).findIndex((cell) => pattern.test(compactText(cell)));
  }

  /**
   * Locate the header row: the first row (within HEADER_SCAN_ROWS) holding a
   * 學號 column. 姓名 sits in the same row in every known layout; 備註 can sit
   * one row higher when the header is two rows deep, so it is searched upward.
   */
  function detectHeader(rows) {
    const limit = Math.min(rows.length, HEADER_SCAN_ROWS);
    for (let r = 0; r < limit; r += 1) {
      const idCol = findColumn(rows[r], ID_HEADER_PATTERN);
      if (idCol === -1) continue;
      let remarkCol = -1;
      for (let up = r; up >= 0 && remarkCol === -1; up -= 1) {
        remarkCol = findColumn(rows[up], REMARK_HEADER_PATTERN);
      }
      return {
        headerRow: r,
        idCol,
        nameCol: findColumn(rows[r], NAME_HEADER_PATTERN),
        remarkCol,
      };
    }
    return null;
  }

  /**
   * Parse one sheet into student records. Rows whose 學號 cell is not a 學號
   * (blank spacer rows, repeated headers, totals) are skipped.
   */
  function parseSheet(rows) {
    const header = detectHeader(rows);
    if (!header) return { header: null, records: [] };
    const cell = (row, col) => (col === -1 ? "" : row[col]);
    const records = rows
      .slice(header.headerRow + 1)
      .map((row, offset) => ({ row: row || [], rowIndex: header.headerRow + 1 + offset }))
      .map(({ row, rowIndex }) => ({
        rowIndex,
        id: normalizeStudentId(cell(row, header.idCol)),
        rawId: compactText(cell(row, header.idCol)),
        name: normalizeName(cell(row, header.nameCol)),
        remark: String(cell(row, header.remarkCol) ?? "").trim(),
        row,
      }))
      .filter((record) => record.id !== "");
    return { header, records };
  }

  function appendTo(map, key, value) {
    if (!key) return map;
    const existing = map.get(key) || [];
    return new Map(map).set(key, [...existing, value]);
  }

  /**
   * Build lookup maps over every parsed 獎勵名冊 sheet.
   * @param sources [{ fileName, sheetName, records }]
   */
  function buildRenewalIndex(sources) {
    return sources.reduce(
      (index, source) =>
        source.records.reduce((acc, record) => {
          const entry = {
            fileName: source.fileName,
            sheetName: source.sheetName,
            rowNumber: record.rowIndex + 1,
            id: record.id,
            name: record.name,
            remark: record.remark,
          };
          return {
            byId: appendTo(acc.byId, record.id, entry),
            byName: appendTo(acc.byName, record.name, entry),
          };
        }, index),
      { byId: new Map(), byName: new Map() },
    );
  }

  function classifyApplicant(applicant, index) {
    const idHits = index.byId.get(applicant.id) || [];
    if (idHits.length > 0) {
      const nameMismatch =
        applicant.name !== "" && idHits.some((hit) => hit.name !== "" && hit.name !== applicant.name);
      return { status: STATUS.MATCHED, hits: idHits, nameMismatch };
    }
    const nameHits = applicant.name ? index.byName.get(applicant.name) || [] : [];
    if (nameHits.length > 0) {
      return { status: STATUS.NAME_ONLY, hits: nameHits, nameMismatch: false };
    }
    return { status: STATUS.NONE, hits: [], nameMismatch: false };
  }

  /** Compare every applicant record against the index. */
  function compareApplicants(applicants, index) {
    return applicants.map((applicant) => ({ ...applicant, ...classifyApplicant(applicant, index) }));
  }

  function describeSource(hit) {
    const file = hit.fileName.replace(/\.[^.]+$/, "");
    return `${file}／${hit.sheetName}（第 ${hit.rowNumber} 列）`;
  }

  function summarize(results) {
    const count = (status) => results.filter((r) => r.status === status).length;
    return {
      total: results.length,
      matched: count(STATUS.MATCHED),
      nameOnly: count(STATUS.NAME_ONLY),
      none: count(STATUS.NONE),
      nameMismatch: results.filter((r) => r.nameMismatch).length,
    };
  }

  return {
    STATUS,
    STATUS_LABELS,
    normalizeStudentId,
    normalizeName,
    detectHeader,
    parseSheet,
    buildRenewalIndex,
    compareApplicants,
    describeSource,
    summarize,
  };
});
