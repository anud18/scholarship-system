/*
 * 續領名單比對 — step 2: the 獎勵名冊 file list.
 *
 * Files accumulate across picks/drops (a file with the same name replaces the
 * earlier one). Each file is a card listing its sheets with a checkbox, so an
 * admin can leave out a year or a 備取 sheet; sheets without a 學號 column or
 * without data are shown as skipped. onChange receives the included sheets.
 */
(function () {
  "use strict";

  const RC = window.RenewalCompare;
  const { el } = window.RenewalDom;

  function sheetKey(fileName, sheetName) {
    return `${fileName}\u0000${sheetName}`;
  }

  function skipReason(sheet) {
    if (!sheet.header) return "找不到「學號」欄";
    if (sheet.records.length === 0) return "沒有學號資料";
    return null;
  }

  function mount({ list, summary, readWorkbook, sheetRows, onChange }) {
    let files = []; // [{ fileName, status: "loading"|"ready"|"error", error, sheets }]
    let excluded = new Set(); // sheetKey of sheets the admin unticked

    const usableSheets = (file) => file.sheets.filter((sheet) => !skipReason(sheet));
    const isIncluded = (file, sheet) => !excluded.has(sheetKey(file.fileName, sheet.sheetName));

    function includedSheets() {
      return files
        .filter((file) => file.status === "ready")
        .flatMap((file) => usableSheets(file).filter((sheet) => isIncluded(file, sheet)));
    }

    function update(nextFiles, nextExcluded) {
      files = nextFiles;
      excluded = nextExcluded;
      render();
      onChange(includedSheets());
    }

    async function parse(file) {
      try {
        const { workbook } = await readWorkbook(file);
        const sheets = workbook.SheetNames.map((sheetName) => ({
          fileName: file.name,
          sheetName,
          ...RC.parseSheet(sheetRows(workbook, sheetName)),
        }));
        return { fileName: file.name, status: "ready", error: null, sheets };
      } catch (error) {
        console.error("renewal file", file.name, error);
        return { fileName: file.name, status: "error", error: error.message, sheets: [] };
      }
    }

    async function addFiles(newFiles) {
      const names = new Set(newFiles.map((f) => f.name));
      const placeholder = (name) => ({ fileName: name, status: "loading", error: null, sheets: [] });
      const existing = new Set(files.map((f) => f.fileName));
      const keepExcluded = new Set([...excluded].filter((key) => !names.has(key.split("\u0000")[0])));
      // A re-added file keeps its card position; new files go to the end.
      update(
        [
          ...files.map((f) => (names.has(f.fileName) ? placeholder(f.fileName) : f)),
          ...[...names].filter((name) => !existing.has(name)).map(placeholder),
        ],
        keepExcluded,
      );
      const parsed = await Promise.all(newFiles.map(parse));
      const byName = new Map(parsed.map((p) => [p.fileName, p]));
      update(files.map((f) => byName.get(f.fileName) || f), excluded);
    }

    function removeFile(fileName) {
      const keepExcluded = new Set([...excluded].filter((key) => key.split("\u0000")[0] !== fileName));
      update(files.filter((f) => f.fileName !== fileName), keepExcluded);
    }

    function toggleSheet(fileName, sheetName, include) {
      const key = sheetKey(fileName, sheetName);
      const next = new Set(excluded);
      if (include) next.delete(key);
      else next.add(key);
      update(files, next);
    }

    function setAllSheets(file, include) {
      const keys = usableSheets(file).map((sheet) => sheetKey(file.fileName, sheet.sheetName));
      const next = new Set(excluded);
      keys.forEach((key) => (include ? next.delete(key) : next.add(key)));
      update(files, next);
    }

    // ---- rendering --------------------------------------------------------

    function renderSheetRow(file, sheet) {
      const reason = skipReason(sheet);
      const included = !reason && isIncluded(file, sheet);
      const checkbox = el("input", {
        type: "checkbox",
        checked: included,
        disabled: Boolean(reason),
        "aria-label": `納入 ${sheet.sheetName}`,
        onChange: (event) => toggleSheet(file.fileName, sheet.sheetName, event.target.checked),
      });
      const meta = reason
        ? el("span", { className: "chip skipped", text: `略過：${reason}` })
        : el("span", { className: "sheet-count", text: `${sheet.records.length} 筆` });
      return el("li", { className: `sheet-row${included ? "" : " off"}` }, [
        el("label", {}, [checkbox, el("span", { className: "sheet-name", text: sheet.sheetName, title: sheet.sheetName })]),
        meta,
      ]);
    }

    function renderFileMeta(file) {
      if (file.status === "loading") return el("span", { className: "file-meta", text: "讀取中…" });
      if (file.status === "error") return el("span", { className: "file-meta error", text: `無法讀取：${file.error}` });
      const usable = usableSheets(file);
      const included = usable.filter((sheet) => isIncluded(file, sheet));
      const count = included.reduce((sum, sheet) => sum + sheet.records.length, 0);
      const skipped = file.sheets.length - usable.length;
      const parts = [`已納入 ${included.length}/${usable.length} 個工作表`, `${count} 筆`];
      if (skipped > 0) parts.push(`${skipped} 個略過`);
      return el("span", { className: "file-meta", text: parts.join(" · ") });
    }

    function renderFileCard(file) {
      const header = el("div", { className: "file-head" }, [
        el("span", { className: "file-icon", "aria-hidden": "true", text: "XLS" }),
        el("div", { className: "file-title" }, [
          el("span", { className: "file-name", text: file.fileName, title: file.fileName }),
          renderFileMeta(file),
        ]),
        el("button", {
          type: "button",
          className: "icon-button",
          "aria-label": `移除 ${file.fileName}`,
          title: "移除此檔案",
          text: "✕",
          onClick: () => removeFile(file.fileName),
        }),
      ]);
      if (file.status !== "ready" || file.sheets.length === 0) {
        return el("li", { className: `file-card ${file.status}` }, [header]);
      }
      const bulk = usableSheets(file).length > 1
        ? el("div", { className: "bulk" }, [
            el("button", { type: "button", className: "link", text: "全選", onClick: () => setAllSheets(file, true) }),
            el("button", { type: "button", className: "link", text: "全不選", onClick: () => setAllSheets(file, false) }),
          ])
        : null;
      const details = el("details", { className: "sheets" }, [
        el("summary", { text: `工作表明細（${file.sheets.length}）` }),
        bulk,
        el("ul", { className: "sheet-rows" }, file.sheets.map((sheet) => renderSheetRow(file, sheet))),
      ]);
      return el("li", { className: "file-card ready" }, [header, details]);
    }

    function render() {
      // Keep <details> open state across re-renders.
      const openFiles = new Set(
        [...list.querySelectorAll("details[open]")].map((d) => d.closest(".file-card").dataset.file),
      );
      list.replaceChildren(
        ...files.map((file) => {
          const card = renderFileCard(file);
          card.dataset.file = file.fileName;
          const details = card.querySelector("details");
          if (details && openFiles.has(file.fileName)) details.open = true;
          return card;
        }),
      );
      renderSummary();
    }

    function renderSummary() {
      if (files.length === 0) {
        summary.hidden = true;
        return;
      }
      const sheets = includedSheets();
      const count = sheets.reduce((sum, sheet) => sum + sheet.records.length, 0);
      const fileCount = new Set(sheets.map((sheet) => sheet.fileName)).size;
      summary.hidden = false;
      summary.replaceChildren(
        el("span", { text: `比對範圍：${fileCount} 個檔案 · ${sheets.length} 個工作表 · 共 ${count} 筆` }),
        el("button", { type: "button", className: "link", text: "全部清除", onClick: () => update([], new Set()) }),
      );
    }

    render();
    return { addFiles };
  }

  window.RenewalFiles = { mount };
})();
