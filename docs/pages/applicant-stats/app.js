/* 申請人數統計 — page wiring. All parsing happens in this tab; see stats.js. */
(function () {
  "use strict";

  const RC = window.RenewalCompare;
  const AS = window.ApplicantStats;
  const Export = window.ApplicantStatsExport;
  const { $, el, bindDropZone } = window.RenewalDom;

  // Each report becomes one tab on the page and one sheet in the download.
  const REPORTS = Object.freeze([
    {
      key: "byGrade",
      tab: "各年級申請人數",
      sheetName: "統計各學院-各年級學生人數",
      titleSuffix: "統計各學院各年級申請人數",
      caption: "所有申請學生，依學院 × 年級計數。",
    },
    {
      key: "foreignNstc",
      tab: "外籍生國科會申請人數",
      sheetName: "統計各學院-外籍生國科會人數",
      titleSuffix: "統計各學院外籍生國科會申請人數",
      caption: "國籍不是中華民國，且申請類別包含國科會（含國科會為第一或第二志願）的學生，依學院 × 國籍計數；最後一欄為國籍分布概況。",
    },
  ]);

  let state = { fileName: "", prefix: "", reports: null, activeKey: REPORTS[0].key };

  function setState(patch) {
    state = { ...state, ...patch };
  }

  async function loadFile(file) {
    const status = $("applicant-status");
    status.className = "status";
    status.textContent = "讀取中…";
    try {
      const workbook = XLSX.read(await file.arrayBuffer(), { type: "array" });
      const sheet = workbook.SheetNames.map((sheetName) => {
        const rows = XLSX.utils.sheet_to_json(workbook.Sheets[sheetName], { header: 1, defval: null, raw: true });
        return { sheetName, rows, ...RC.parseSheet(rows) };
      }).find((s) => s.header !== null);
      if (!sheet) throw new Error("找不到含「學號」欄位的工作表，請確認檔案是否為申請資料彙整表。");
      if (sheet.records.length === 0) throw new Error(`工作表「${sheet.sheetName}」沒有任何學號資料。`);

      const reports = AS.buildReports(sheet.records, sheet.rows[sheet.header.headerRow]);
      const titleCell = sheet.header.headerRow > 0 ? sheet.rows[0][0] : null;
      setState({ fileName: file.name, prefix: AS.reportPrefix(titleCell, file.name), reports });
      status.textContent = `工作表「${sheet.sheetName}」：讀到 ${reports.applicantCount} 位申請學生`;
    } catch (error) {
      console.error("applicant file", error);
      setState({ reports: null });
      status.className = "status error";
      status.textContent = `無法讀取：${error.message}`;
    }
    render();
  }

  // ---- rendering ----------------------------------------------------------

  function numberCell(value, bold) {
    return el("td", { className: `num${value === 0 ? " zero" : ""}${bold ? " strong" : ""}`, text: String(value) });
  }

  function renderTable(table) {
    const labels = Export.headerLabels(table).map(String);
    const numeric = Export.numericColumnCount(table);
    const cells = (values, bold) =>
      values.map((value, i) =>
        i < numeric
          ? numberCell(value, bold || i === numeric - 1)
          : el("td", { className: `distribution${bold ? " strong" : ""}`, text: value }),
      );
    $("stats-head").replaceChildren(
      el("tr", {}, [
        el("th", { text: "編號" }),
        el("th", { text: "學院/年級" }),
        ...labels.map((label, i) => {
          const isGrade = i < table.columns.length && typeof table.columns[i].label === "number";
          return el("th", { className: i < numeric ? "num" : "", text: isGrade ? `${label} 年級` : label });
        }),
      ]),
    );
    $("stats-body").replaceChildren(
      ...table.rows.map((row) =>
        el("tr", { className: row.total === 0 ? "empty-row" : "" }, [
          el("td", { className: "num", text: row.no == null ? "" : String(row.no) }),
          el("td", { text: row.label }),
          ...cells(Export.rowValues(table, row), false),
        ]),
      ),
    );
    $("stats-foot").replaceChildren(
      el("tr", { className: "total" }, [
        el("td", {}),
        el("td", { text: "合計" }),
        ...cells(Export.rowValues(table, table.totals), true),
      ]),
    );
  }

  function renderTabs() {
    const tabs = REPORTS.map((report) =>
      el("button", {
        type: "button",
        role: "tab",
        "aria-selected": String(report.key === state.activeKey),
        "aria-pressed": String(report.key === state.activeKey),
        text: `${report.tab}（${state.reports[report.key].totals.total}）`,
        onClick: () => {
          setState({ activeKey: report.key });
          render();
        },
      }),
    );
    $("tabs").replaceChildren(...tabs);
  }

  function renderWarnings(warnings) {
    const list = $("warnings");
    list.hidden = warnings.length === 0;
    list.replaceChildren(...warnings.map((text) => el("li", { text })));
  }

  function render() {
    $("results").hidden = state.reports === null;
    if (!state.reports) return;
    const active = REPORTS.find((r) => r.key === state.activeKey);
    renderWarnings(state.reports.warnings);
    renderTabs();
    $("report-caption").textContent = active.caption;
    renderTable(state.reports[active.key]);
  }

  // ---- wiring -------------------------------------------------------------

  async function download(event) {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const reports = REPORTS.map((report) => ({
        sheetName: report.sheetName,
        title: `${state.prefix} ${report.titleSuffix}`.trim(),
        table: state.reports[report.key],
      }));
      await Export.downloadReports(reports, `${state.prefix || "申請人數"}_申請人數統計.xlsx`);
    } catch (error) {
      console.error("export", error);
      window.alert(`匯出失敗：${error.message}`);
    } finally {
      button.disabled = false;
    }
  }

  bindDropZone($("applicant-drop"), $("applicant-file"), ([file]) => loadFile(file));
  $("download").addEventListener("click", download);

  if (typeof XLSX === "undefined" || typeof ExcelJS === "undefined") {
    $("applicant-status").className = "status error";
    $("applicant-status").textContent = "Excel 元件載入失敗，請檢查網路後重新整理頁面。";
  }
})();
