// Run: node --test docs/pages/applicant-stats/stats.test.js
// Fixtures are synthetic — never paste rows from the real 彙整表 (they hold PII).
const test = require("node:test");
const assert = require("node:assert/strict");
const RC = require("../renewal-compare/compare.js");
const AS = require("./stats.js");

test("resolveCollege maps the 彙整表 numbered short names to template names", () => {
  assert.deepEqual(AS.resolveCollege("16. 醫學院"), { index: 15, label: "醫學院" });
  assert.deepEqual(AS.resolveCollege("1. 人社院"), { index: 0, label: "人文藝術與社會學院" });
  assert.deepEqual(AS.resolveCollege("15. 生醫工學院"), { index: 14, label: "生物醫學暨工程學院" });
  assert.deepEqual(AS.resolveCollege("工程生物學院"), { index: 2, label: "工程生物科學學院" });
  assert.deepEqual(AS.resolveCollege("國際半導體產業學院"), { index: 10, label: "國際半導體產業學院" });
});

test("resolveCollege keeps unknown colleges visible instead of dropping them", () => {
  assert.deepEqual(AS.resolveCollege("99. 外太空學院"), { index: -1, label: "外太空學院" });
  assert.deepEqual(AS.resolveCollege(""), { index: -1, label: "（未填學院）" });
});

test("parseGrade accepts numbers and 博N text, rejects blanks", () => {
  assert.equal(AS.parseGrade(3), 3);
  assert.equal(AS.parseGrade(" 4 "), 4);
  assert.equal(AS.parseGrade("博2"), 2);
  assert.equal(AS.parseGrade(""), null);
  assert.equal(AS.parseGrade("逕博二"), null);
  assert.equal(AS.parseGrade(0), null);
});

test("isForeign / appliesNstc", () => {
  assert.equal(AS.isForeign("中華民國"), false);
  assert.equal(AS.isForeign("臺灣"), false);
  assert.equal(AS.isForeign(""), false);
  assert.equal(AS.isForeign("越南"), true);
  assert.equal(AS.appliesNstc("國科會博士生獎學金"), true);
  assert.equal(AS.appliesNstc("教育部博士生獎學金(第一志願)暨國科會博士生獎學金(第二志願)"), true);
  assert.equal(AS.appliesNstc("115學年度教育部博士生獎學金"), false);
});

const SHEET = [
  ["115學年度博士生獎學金學生資料彙整表 - 全校"],
  ["NO.", "學院初審會議之學院排序", "申請獎學金類別", "學院", "年級", "學生中文姓名", "國籍", "學號"],
  [1, "", "國科會博士生獎學金", "16. 醫學院", 1, "甲", "中華民國", "413000001"],
  [2, "", "國科會博士生獎學金", "16. 醫學院", 1, "乙", "越南", "413000002"],
  [3, "", "教育部(第一志願)暨國科會(第二志願)", "7. 電機學院", 3, "丙", "印度", "413000003"],
  [4, "", "教育部博士生獎學金", "7. 電機學院", 3, "丁", "印度", "413000004"],
  [5, "", "國科會博士生獎學金", "99. 外太空學院", "", "戊", "", "413000005"],
];

test("buildReports tallies college × 年級 and the foreign 國科會 subset", () => {
  const { header, records } = RC.parseSheet(SHEET);
  const report = AS.buildReports(records, SHEET[header.headerRow]);
  const row = (table, label) => table.rows.find((r) => r.label === label);

  assert.equal(report.applicantCount, 5);
  assert.equal(report.byGrade.grades.length, 9);
  assert.equal(report.byGrade.rows.length, 20); // 19 template colleges + 外太空學院
  assert.deepEqual(row(report.byGrade, "醫學院").counts.slice(0, 3), [2, 0, 0]);
  assert.equal(row(report.byGrade, "電機學院").total, 2);
  assert.equal(row(report.byGrade, "外太空學院").unknownGrade, 1);
  assert.equal(row(report.byGrade, "人文藝術與社會學院").total, 0);
  assert.equal(report.byGrade.hasUnknownGrade, true);
  assert.equal(report.byGrade.totals.total, 5);
  assert.equal(report.byGrade.totals.counts[0], 2);

  // 乙 (越南, 國科會) + 丙 (印度, 第二志願 國科會); 丁 is 教育部 only, 戊 has no 國籍.
  assert.equal(report.foreignNstc.totals.total, 2);
  assert.equal(row(report.foreignNstc, "醫學院").counts[0], 1);
  assert.equal(row(report.foreignNstc, "電機學院").counts[2], 1);
  assert.equal(report.foreignNstc.hasUnknownGrade, false);

  assert.deepEqual(report.warnings, [
    "學院無法對應到 19 個學院：第 7 列",
    "年級空白或無法辨識：第 7 列",
    "國籍空白（不計入外籍生）：第 7 列",
  ]);
});

test("grade columns grow past 9 when the data has higher grades", () => {
  const applicants = [{ college: { index: 0, label: "人文藝術與社會學院" }, grade: 11 }];
  assert.equal(AS.tallyByCollegeGrade(applicants).grades.length, 11);
});

test("reportPrefix reads the 彙整表 title, falling back to the file name", () => {
  assert.equal(AS.reportPrefix("115學年度博士生獎學金學生資料彙整表 - 全校", "x.xlsx"), "115學年度博士生獎學金");
  assert.equal(AS.reportPrefix(null, "114學年度博士生獎學金學生資料彙整表_全校.xlsx"), "114學年度博士生獎學金");
});
