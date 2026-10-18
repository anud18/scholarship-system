// Run: node --test docs/pages/renewal-compare/
// Fixtures are synthetic — never paste rows from the real 名冊 (they hold PII).
const test = require("node:test");
const assert = require("node:assert/strict");
const RC = require("./compare.js");

test("normalizeStudentId restores IDs that lost their leading zero", () => {
  assert.equal(RC.normalizeStudentId(856001), RC.normalizeStudentId("0856001"));
  assert.equal(RC.normalizeStudentId(" 312345678 "), "312345678");
  assert.equal(RC.normalizeStudentId("\t312345678"), "312345678");
  assert.equal(RC.normalizeStudentId("312345678.0"), "312345678");
  assert.equal(RC.normalizeStudentId("a1234567"), "A1234567");
});

test("normalizeStudentId rejects non-學號 cells", () => {
  ["", null, undefined, "學號", "1", "合計", "S223456789X"].forEach((value) =>
    assert.equal(RC.normalizeStudentId(value), ""),
  );
});

test("detectHeader finds 學號/姓名 on a deep header and 備註 one row above", () => {
  const rows = [
    ["113年 獎勵名冊"],
    ["計畫編號"],
    ["序號", "基本資料", null, null, null, "學籍資料", null, "備註"],
    [null, "學院", "系所", "姓名", "國籍", "註冊入學日期", "學號", null],
    [1, "工學院", "材料系", "王小明", "中華民國", "113.9.1", 413000001, "逕博"],
  ];
  assert.deepEqual(RC.detectHeader(rows), { headerRow: 3, idCol: 6, nameCol: 3, remarkCol: 7 });
});

test("detectHeader picks 學生中文姓名, not 英文姓名 or 教授姓名", () => {
  const rows = [["彙整表"], ["NO.", "學生中文姓名", "學生英文姓名", "學號", "學生身分證字號", "指導教授姓名"]];
  assert.deepEqual(RC.detectHeader(rows), { headerRow: 1, idCol: 3, nameCol: 1, remarkCol: -1 });
});

test("detectHeader returns null when a sheet has no 學號 column", () => {
  assert.equal(RC.detectHeader([["說明"], ["本頁無名單"]]), null);
});

test("parseSheet skips spacer rows, repeated headers and blanks", () => {
  const rows = [
    ["編號", "姓名", "學號"],
    [null, null, null],
    [1, "王 小明", 413000001],
    [null, null, "學號"],
    [2, "李小華", "0756002"],
  ];
  const { records } = RC.parseSheet(rows);
  assert.deepEqual(
    records.map(({ id, name, rowIndex }) => ({ id, name, rowIndex })),
    [
      { id: "413000001", name: "王小明", rowIndex: 2 },
      { id: "756002", name: "李小華", rowIndex: 4 },
    ],
  );
});

function indexFrom(sheets) {
  return RC.buildRenewalIndex(
    sheets.map(([sheetName, rows]) => ({ fileName: "名冊.xlsx", sheetName, ...RC.parseSheet(rows) })),
  );
}

test("compareApplicants classifies by 學號 first, then by name", () => {
  const index = indexFrom([
    ["112年", [["姓名", "學號", "備註"], ["王小明", 413000001, "逕博"], ["陳大同", 756002, null]]],
    ["113年", [["姓名", "學號"], ["王小明", 413000001]]],
  ]);
  const applicants = RC.parseSheet([
    ["學生中文姓名", "學號"],
    ["王小明", "413000001"],
    ["陳大同改", "0756002"],
    ["林美美", "414000009"],
    ["陳大同", "414000010"],
  ]).records;

  const results = RC.compareApplicants(applicants, index);
  assert.deepEqual(
    results.map((r) => [r.status, r.hits.length, r.nameMismatch]),
    [
      [RC.STATUS.MATCHED, 2, false],
      [RC.STATUS.MATCHED, 1, true],
      [RC.STATUS.NONE, 0, false],
      [RC.STATUS.NAME_ONLY, 1, false],
    ],
  );
  assert.equal(results[0].hits[0].remark, "逕博");
  assert.equal(RC.describeSource(results[0].hits[1]), "名冊／113年（第 2 列）");
  assert.deepEqual(RC.summarize(results), { total: 4, matched: 2, nameOnly: 1, none: 1, nameMismatch: 1 });
});

test("buildRenewalIndex does not mutate earlier maps", () => {
  const first = indexFrom([["A", [["姓名", "學號"], ["甲", 413000001]]]]);
  const sizeBefore = first.byId.size;
  RC.buildRenewalIndex([{ fileName: "x.xlsx", sheetName: "B", records: RC.parseSheet([["學號"], [413000002]]).records }]);
  assert.equal(first.byId.size, sizeBefore);
});
