/* 續領名單比對 — page wiring. All parsing happens in this tab; see compare.js. */
(function () {
  "use strict";

  const RC = window.RenewalCompare;
  const { STATUS, STATUS_LABELS } = RC;

  // Applicant columns shown in the table, located by header text.
  const DISPLAY_COLUMNS = Object.freeze({
    no: /^(NO\.?|編號|序號)$/i,
    college: /^學院($|\()/, // not 學院初審會議之學院排序
    department: /^系所/,
    grade: /^年級/,
    category: /^申請獎學金類別/,
  });

  const FILTERS = Object.freeze([
    { key: "all", label: "全部" },
    { key: STATUS.MATCHED, label: "在續領名單" },
    { key: STATUS.NAME_ONLY, label: "需人工確認" },
    { key: STATUS.NONE, label: "不在名單" },
  ]);

  const $ = (id) => document.getElementById(id);

  let state = {
    applicant: null, // { fileName, data, sheetName, rows, origin, columnCount, header, records }
    renewals: [], // [{ fileName, sheetName, records }]
    results: [],
    filter: "all",
    query: "",
  };

  function setState(patch) {
    state = { ...state, ...patch };
  }

  function el(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([key, value]) => {
      if (key === "text") node.textContent = value;
      else if (key === "className") node.className = value;
      else node.setAttribute(key, value);
    });
    (children || []).forEach((child) => node.append(child));
    return node;
  }

  async function readWorkbook(file) {
    const data = await file.arrayBuffer();
    return { data, workbook: XLSX.read(data, { type: "array" }) };
  }

  /** Top-left cell and width of a sheet's used range (rows are relative to it). */
  function sheetBounds(workbook, sheetName) {
    const range = XLSX.utils.decode_range(workbook.Sheets[sheetName]["!ref"] || "A1");
    return { origin: range.s, columnCount: range.e.c - range.s.c + 1 };
  }

  function sheetRows(workbook, sheetName) {
    return XLSX.utils.sheet_to_json(workbook.Sheets[sheetName], { header: 1, defval: null, raw: true });
  }

  function cellText(value) {
    return value == null ? "" : String(value).trim();
  }

  // ---- loading ----------------------------------------------------------

  async function loadApplicantFile(file) {
    const status = $("applicant-status");
    status.className = "status";
    status.textContent = "讀取中…";
    try {
      const { data, workbook } = await readWorkbook(file);
      const parsed = workbook.SheetNames.map((sheetName) => {
        const rows = sheetRows(workbook, sheetName);
        return { sheetName, rows, ...sheetBounds(workbook, sheetName), ...RC.parseSheet(rows) };
      }).find((sheet) => sheet.header !== null);
      if (!parsed) throw new Error("找不到含「學號」欄位的工作表，請確認檔案是否為申請資料彙整表。");
      if (parsed.records.length === 0) throw new Error(`工作表「${parsed.sheetName}」沒有任何學號資料。`);
      setState({ applicant: { fileName: file.name, data, ...parsed } });
      const nameNote = parsed.header.nameCol === -1 ? "（未找到姓名欄，將只用學號比對）" : "";
      status.textContent = `工作表「${parsed.sheetName}」：讀到 ${parsed.records.length} 位申請學生${nameNote}`;
    } catch (error) {
      console.error("applicant file", error);
      setState({ applicant: null });
      status.className = "status error";
      status.textContent = `無法讀取：${error.message}`;
    }
    render();
  }

  async function parseRenewalFile(file) {
    try {
      const { workbook } = await readWorkbook(file);
      const sheets = workbook.SheetNames.map((sheetName) => ({
        fileName: file.name,
        sheetName,
        ...RC.parseSheet(sheetRows(workbook, sheetName)),
      }));
      return { fileName: file.name, sheets, error: null };
    } catch (error) {
      console.error("renewal file", file.name, error);
      return { fileName: file.name, sheets: [], error: error.message };
    }
  }

  async function loadRenewalFiles(files) {
    const list = $("renewal-status");
    list.replaceChildren(el("li", { text: "讀取中…" }));
    const parsedFiles = await Promise.all(files.map(parseRenewalFile));
    list.replaceChildren(...parsedFiles.flatMap(renderRenewalStatus));
    const renewals = parsedFiles.flatMap((f) => f.sheets).filter((s) => s.records.length > 0);
    setState({ renewals });
    render();
  }

  function renderRenewalStatus(parsedFile) {
    if (parsedFile.error) {
      return [el("li", { className: "error", text: `${parsedFile.fileName}：無法讀取（${parsedFile.error}）` })];
    }
    return parsedFile.sheets.map((sheet) => {
      const label = `${parsedFile.fileName}／${sheet.sheetName}`;
      if (!sheet.header) return el("li", { className: "skipped", text: `${label}：未找到「學號」欄，已略過` });
      if (sheet.records.length === 0) return el("li", { className: "skipped", text: `${label}：沒有學號資料，已略過` });
      return el("li", { text: `${label}：${sheet.records.length} 筆` });
    });
  }

  // ---- rendering ----------------------------------------------------------

  function displayColumns(applicant) {
    const headerRow = applicant.rows[applicant.header.headerRow] || [];
    return Object.fromEntries(
      Object.entries(DISPLAY_COLUMNS).map(([key, pattern]) => [
        key,
        headerRow.findIndex((cell) => pattern.test(cellText(cell).replace(/\s+/g, ""))),
      ]),
    );
  }

  function render() {
    const { applicant, renewals } = state;
    const ready = applicant !== null && renewals.length > 0;
    $("results").hidden = !ready;
    if (!ready) return;

    const index = RC.buildRenewalIndex(renewals);
    const columns = displayColumns(applicant);
    const pick = (row, col) => (col === -1 ? "" : cellText(row[col]));
    const results = RC.compareApplicants(applicant.records, index).map((result) => ({
      ...result,
      no: pick(result.row, columns.no),
      college: pick(result.row, columns.college),
      department: pick(result.row, columns.department),
      grade: pick(result.row, columns.grade),
      category: pick(result.row, columns.category),
    }));
    setState({ results });
    renderSummary(RC.summarize(results));
    renderFilters();
    renderRows();
  }

  function renderSummary(summary) {
    const stat = (value, label) => el("div", { className: "stat" }, [el("b", { text: String(value) }), el("span", { text: label })]);
    const stats = [
      stat(summary.total, "申請學生"),
      stat(summary.matched, "在續領名單"),
      stat(summary.nameOnly, "需人工確認"),
      stat(summary.none, "不在名單"),
    ];
    if (summary.nameMismatch > 0) stats.push(stat(summary.nameMismatch, "學號相符但姓名不同"));
    $("summary").replaceChildren(...stats);
  }

  function renderFilters() {
    const buttons = FILTERS.map(({ key, label }) => {
      const button = el("button", { type: "button", "aria-pressed": String(state.filter === key), text: label });
      button.addEventListener("click", () => {
        setState({ filter: key });
        renderFilters();
        renderRows();
      });
      return button;
    });
    $("filters").replaceChildren(...buttons);
  }

  function matchesQuery(result, query) {
    if (!query) return true;
    return [result.name, result.rawId, result.college, result.department, result.category]
      .some((value) => value.toLowerCase().includes(query));
  }

  function visibleResults() {
    const query = state.query.trim().toLowerCase();
    return state.results
      .filter((r) => state.filter === "all" || r.status === state.filter)
      .filter((r) => matchesQuery(r, query));
  }

  function renderHits(result) {
    if (result.hits.length === 0) return "";
    const items = result.hits.map((hit) => {
      const extra = result.status === STATUS.NAME_ONLY ? `　名冊學號 ${hit.id}` : "";
      const children = [RC.describeSource(hit) + extra];
      if (hit.name && hit.name !== result.name) children.push(el("span", { className: "remark", text: `　名冊姓名：${hit.name}` }));
      if (hit.remark) children.push(el("span", { className: "remark", text: `　備註：${hit.remark}` }));
      return el("li", {}, children);
    });
    return el("ul", { className: "hits" }, items);
  }

  function renderStatus(result) {
    const children = [el("span", { className: `badge ${result.status}`, text: STATUS_LABELS[result.status] })];
    if (result.nameMismatch) children.push(el("span", { className: "mismatch", text: "學號相符但姓名不同" }));
    return el("td", {}, children);
  }

  function renderRows() {
    const rows = visibleResults().map((result) =>
      el("tr", {}, [
        el("td", { className: "nowrap", text: result.no }),
        el("td", { text: result.college }),
        el("td", { text: result.department }),
        el("td", { className: "nowrap", text: result.grade }),
        el("td", { className: "nowrap", text: result.name }),
        el("td", { className: "nowrap", text: result.rawId }),
        el("td", { text: result.category }),
        renderStatus(result),
        el("td", {}, [renderHits(result)]),
      ]),
    );
    $("result-rows").replaceChildren(...rows);
    $("empty").hidden = rows.length > 0;
  }

  // ---- wiring -------------------------------------------------------------

  $("applicant-file").addEventListener("change", (event) => {
    const [file] = event.target.files;
    if (file) loadApplicantFile(file);
  });
  $("renewal-files").addEventListener("change", (event) => {
    const files = [...event.target.files];
    if (files.length > 0) loadRenewalFiles(files);
  });
  $("search").addEventListener("input", (event) => {
    setState({ query: event.target.value });
    renderRows();
  });
  $("download").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await window.RenewalExport.downloadComparison(state.applicant, state.results);
    } catch (error) {
      console.error("export", error);
      window.alert(`匯出失敗：${error.message}`);
    } finally {
      button.disabled = false;
    }
  });

  if (typeof XLSX === "undefined") {
    $("applicant-status").className = "status error";
    $("applicant-status").textContent = "Excel 解析元件載入失敗，請檢查網路後重新整理頁面。";
  }
})();
