/*
 * 申請人數統計 — .xlsx export with ExcelJS, styled after the office template
 * 「統計各學院各年級申請人數.xlsx」: merged bold title, 微軟正黑體, thin borders
 * on every cell, bold 合計 row, SUM formulas for the totals.
 */
(function () {
  "use strict";

  const FONT_NAME = "微軟正黑體";
  const FONT_SIZE = 14;
  const ROW_HEIGHT = 21;
  const TITLE_HEIGHT = 30;
  const WIDTHS = Object.freeze({ no: 7, college: 26, count: 10, total: 16, distribution: 48 });
  const THIN = { style: "thin" };
  const BORDER = Object.freeze({ top: THIN, left: THIN, bottom: THIN, right: THIN });
  const HEADER_FILL = { type: "pattern", pattern: "solid", fgColor: { argb: "FFF2F2F2" } };
  const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

  /** Header labels after 編號 / 學院: one per column, 合計, optional 分布概況 text. */
  function headerLabels(table) {
    return [...table.columns.map((c) => c.label), table.totalLabel, ...(table.distributionLabel ? [table.distributionLabel] : [])];
  }

  function rowValues(table, row) {
    return [...row.counts, row.total, ...(table.distributionLabel ? [row.distribution] : [])];
  }

  /** Count + 合計 columns; the 分布概況 column (if any) is text and comes last. */
  function numericColumnCount(table) {
    return table.columns.length + 1;
  }

  function styleCell(cell, { bold = false, align = "center", fill = null } = {}) {
    cell.font = { name: FONT_NAME, size: FONT_SIZE, bold };
    cell.alignment = { horizontal: align, vertical: "middle", wrapText: true };
    cell.border = BORDER;
    if (fill) cell.fill = fill;
  }

  function columnLetter(col) {
    let n = col;
    let letters = "";
    while (n > 0) {
      const rem = (n - 1) % 26;
      letters = String.fromCharCode(65 + rem) + letters;
      n = Math.floor((n - 1) / 26);
    }
    return letters;
  }

  function addStatsSheet(workbook, sheetName, title, table) {
    const sheet = workbook.addWorksheet(sheetName, { views: [{ state: "frozen", ySplit: 2, xSplit: 2 }] });
    const labels = headerLabels(table);
    const lastCol = 2 + labels.length;

    sheet.getColumn(1).width = WIDTHS.no;
    sheet.getColumn(2).width = WIDTHS.college;
    const numeric = numericColumnCount(table);
    const widthOf = (i) => (i >= numeric ? WIDTHS.distribution : i === numeric - 1 ? WIDTHS.total : WIDTHS.count);
    const alignOf = (col) => (col === 2 || col - 3 >= numeric ? "left" : "center");
    labels.forEach((_, i) => {
      sheet.getColumn(3 + i).width = widthOf(i);
    });

    sheet.mergeCells(1, 1, 1, lastCol);
    const titleCell = sheet.getCell(1, 1);
    titleCell.value = title;
    styleCell(titleCell, { bold: true });
    sheet.getRow(1).height = TITLE_HEIGHT;

    const header = sheet.getRow(2);
    header.values = ["編號", "學院/年級", ...labels];
    header.height = ROW_HEIGHT;
    header.eachCell((cell, col) => styleCell(cell, { bold: true, align: alignOf(col), fill: HEADER_FILL }));

    table.rows.forEach((row, i) => {
      const excelRow = sheet.getRow(3 + i);
      excelRow.values = [row.no ?? "", row.label, ...rowValues(table, row)];
      excelRow.height = ROW_HEIGHT;
      excelRow.eachCell({ includeEmpty: true }, (cell, col) => styleCell(cell, { align: alignOf(col) }));
    });

    const firstDataRow = 3;
    const lastDataRow = 2 + table.rows.length;
    const totalRow = sheet.getRow(lastDataRow + 1);
    const totalValues = rowValues(table, table.totals);
    totalRow.getCell(1).value = "";
    totalRow.getCell(2).value = "合計";
    totalValues.forEach((result, i) => {
      const letter = columnLetter(3 + i);
      totalRow.getCell(3 + i).value =
        i < numeric ? { formula: `SUM(${letter}${firstDataRow}:${letter}${lastDataRow})`, result } : result;
    });
    totalRow.height = ROW_HEIGHT;
    totalRow.eachCell({ includeEmpty: true }, (cell, col) =>
      styleCell(cell, { bold: true, align: alignOf(col), fill: HEADER_FILL }),
    );
    return sheet;
  }

  /** reports: [{ sheetName, title, table }] → downloads one workbook. */
  async function downloadReports(reports, fileName) {
    const workbook = new ExcelJS.Workbook();
    // ExcelJS omits cached results equal to 0; have Excel recompute the SUMs on open.
    workbook.calcProperties.fullCalcOnLoad = true;
    reports.forEach(({ sheetName, title, table }) => addStatsSheet(workbook, sheetName, title, table));
    const buffer = await workbook.xlsx.writeBuffer();
    window.RenewalDom.saveBlob(new Blob([buffer], { type: XLSX_MIME }), fileName);
  }

  window.ApplicantStatsExport = { downloadReports, headerLabels, rowValues, numericColumnCount };
})();
