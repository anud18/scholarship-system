/*
 * 續領名單比對 — .xlsx export.
 *
 * For .xlsx uploads the original workbook is re-opened with ExcelJS so its
 * formatting (fonts, borders, widths, merged title, other sheets) survives;
 * the result columns are appended to the right of the 彙整表 sheet and styled
 * like its last column. Other formats (.xls/.csv) fall back to a plain
 * SheetJS rebuild of the values.
 */
(function () {
  "use strict";

  const RC = window.RenewalCompare;
  const { STATUS, STATUS_LABELS } = RC;

  const EXPORT_HEADERS = ["續領比對結果", "名冊出處", "名冊姓名", "名冊備註"];
  const EXPORT_WIDTHS = [18, 48, 12, 36];
  const STATUS_FILLS = Object.freeze({
    [STATUS.MATCHED]: "FFE3F4E8",
    [STATUS.NAME_ONLY]: "FFFDF1D8",
  });
  const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

  function exportValues(result) {
    if (!result) return ["", "", "", ""];
    const label = STATUS_LABELS[result.status] + (result.nameMismatch ? "（學號相符但姓名不同）" : "");
    const unique = (values) => [...new Set(values.filter(Boolean))].join("\n");
    return [
      label,
      result.hits.map(RC.describeSource).join("\n"),
      unique(result.hits.map((hit) => hit.name)),
      unique(result.hits.map((hit) => hit.remark)),
    ];
  }

  function exportFileName(applicant) {
    return `${applicant.fileName.replace(/\.[^.]+$/, "")}_續領比對.xlsx`;
  }

  function saveBlob(blob, fileName) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  // ---- formatted export (ExcelJS, .xlsx only) -----------------------------

  function copyStyle(style) {
    return JSON.parse(JSON.stringify(style || {}));
  }

  /** Widen a full-width title merge above the header to cover the new columns. */
  function extendTitleMerges(sheet, headerRowNo, lastCol, newLastCol) {
    const merges = [...(sheet.model.merges || [])];
    merges.forEach((range) => {
      const [start, end] = range.split(":");
      const startCell = sheet.getCell(start);
      const endCell = sheet.getCell(end);
      const isTitle = endCell.row < headerRowNo && endCell.col === lastCol;
      if (!isTitle) return;
      // Re-merging resets the covered cells' styles; keep the originals and
      // give the new columns the title cell's style.
      const saved = [];
      for (let r = startCell.row; r <= endCell.row; r += 1) {
        for (let c = startCell.col; c <= newLastCol; c += 1) {
          const source = c <= lastCol ? sheet.getCell(r, c) : startCell;
          saved.push({ r, c, style: copyStyle(source.style) });
        }
      }
      sheet.unMergeCells(range);
      sheet.mergeCells(startCell.row, startCell.col, endCell.row, newLastCol);
      saved.forEach(({ r, c, style }) => {
        sheet.getCell(r, c).style = style;
      });
    });
  }

  function styleNewColumns(sheet, firstNewCol, lastCol) {
    const template = sheet.getColumn(lastCol);
    EXPORT_WIDTHS.forEach((width, i) => {
      const column = sheet.getColumn(firstNewCol + i);
      column.width = Math.max(width, template.width || 0);
    });
  }

  function writeRowValues(row, firstNewCol, lastCol, values, fillArgb) {
    const template = row.getCell(lastCol);
    values.forEach((value, i) => {
      const cell = row.getCell(firstNewCol + i);
      const style = copyStyle(template.style);
      cell.style = { ...style, alignment: { ...(style.alignment || {}), wrapText: true, vertical: "top" } };
      if (fillArgb && i === 0) {
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: fillArgb } };
      }
      cell.value = value;
    });
  }

  async function formattedExport(applicant, results) {
    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.load(applicant.data);
    const sheet = workbook.getWorksheet(applicant.sheetName);
    if (!sheet) throw new Error(`找不到工作表「${applicant.sheetName}」`);

    // applicant.rows is relative to the sheet's used range; ExcelJS is 1-based absolute.
    const rowNo = (rowIndex) => applicant.origin.r + rowIndex + 1;
    const lastCol = applicant.origin.c + applicant.columnCount;
    const firstNewCol = lastCol + 1;
    const headerRowNo = rowNo(applicant.header.headerRow);

    extendTitleMerges(sheet, headerRowNo, lastCol, lastCol + EXPORT_HEADERS.length);
    styleNewColumns(sheet, firstNewCol, lastCol);
    writeRowValues(sheet.getRow(headerRowNo), firstNewCol, lastCol, EXPORT_HEADERS, null);
    results.forEach((result) => {
      writeRowValues(
        sheet.getRow(rowNo(result.rowIndex)),
        firstNewCol,
        lastCol,
        exportValues(result),
        STATUS_FILLS[result.status],
      );
    });

    const buffer = await workbook.xlsx.writeBuffer();
    saveBlob(new Blob([buffer], { type: XLSX_MIME }), exportFileName(applicant));
  }

  // ---- plain fallback (SheetJS, values only) ------------------------------

  function plainExport(applicant, results) {
    const resultByRow = new Map(results.map((r) => [r.rowIndex, r]));
    const { headerRow } = applicant.header;
    const rows = applicant.rows;
    const aoa = [
      ...rows.slice(0, headerRow),
      [...(rows[headerRow] || []), ...EXPORT_HEADERS],
      ...rows.slice(headerRow + 1).map((row, offset) => {
        const result = resultByRow.get(headerRow + 1 + offset);
        return result ? [...(row || []), ...exportValues(result)] : row || [];
      }),
    ];
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet(aoa), applicant.sheetName.slice(0, 31));
    XLSX.writeFile(workbook, exportFileName(applicant));
  }

  function canKeepFormatting(applicant) {
    return /\.xlsx$/i.test(applicant.fileName) && typeof ExcelJS !== "undefined";
  }

  /** Download the 彙整表 with the comparison columns appended. */
  async function downloadComparison(applicant, results) {
    if (canKeepFormatting(applicant)) {
      await formattedExport(applicant, results);
    } else {
      plainExport(applicant, results);
    }
  }

  window.RenewalExport = { downloadComparison };
})();
